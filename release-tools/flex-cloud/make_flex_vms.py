#!/usr/bin/env python

__author__ = 'Dibyendu Nath'
__email__ = 'dnath@cs.ucsb.edu'

import sys
import os
import time
import json
import threading
import subprocess
import tempfile
import traceback
import pprint
import argparse
import glob


DEFAULT_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
DEFAULT_MACHINE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "machines.json")

class ShellCommandException(Exception):
    pass


def get_remote_command(user, ip, key_file, command):
    return 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i {0} {1}@{2} "{3}"'.format(key_file, user,
                                                                                                         ip, command)


class ShellCommand(object):
    def __init__(self, cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, verbose=False):
        self.cmd = cmd
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.process = None
        self.verbose = verbose

    def run(self, timeout=None, silent=True):
        def target():
            if self.verbose: print 'Running... $', self.cmd
            self.process = subprocess.Popen(self.cmd,
                                            stdin=self.stdin,
                                            stdout=self.stdout,
                                            stderr=self.stderr,
                                            shell=True)
            self.process.communicate()
            if self.verbose: print 'End of cmd $', self.cmd

        thread = threading.Thread(target=target)
        thread.start()

        if timeout is not None:
            thread.join(timeout)
            if thread.is_alive():
                if silent is False:
                    print 'Terminating process due to timeout...'
                self.process.terminate()
                thread.join()
                if silent is False:
                    print 'Process return code =', self.process.returncode
        else:
            thread.join()
            if self.process.returncode != 0:
                raise ShellCommandException("return code = {0}".format(self.process.returncode))


class VirtualMachine(object):
    NUM_TRIALS = 5
    NUM_SSH_TRIALS = 10

    def __init__(self, ip, username, keyfile, dependencies, python_packages, git_repo,
                 log_type="screen", stderr_log=None, stdout_log=None,
                 keep_existing_stochss_dir=False, verbose=False):
        self.ip = ip
        self.username = username
        self.keyfile = keyfile

        self.dependencies = dependencies
        self.python_packages = python_packages
        self.git_repo = git_repo
        self.keep_existing_stochss_dir = keep_existing_stochss_dir
        self.verbose = verbose

        self.log_type = log_type
        self.stderr_log = stderr_log
        self.stdout_log = stdout_log

    def make_flex_vm(self):
        try:
            self.__is_machine_reachable()
            self.__enable_network_ports()
            self.__try_install_dependencies()
            self.__update_fenics()
            self.__reboot_machine()
            self.__check_fenics_installation()
            self.__try_install_python_packages()
            self.__download_stochss_repo()
            self.__compile_stochss()
            self.run_tests()
            self.__cleanup_instance()

        except:
            traceback.print_exc()


    def __enable_network_ports(self):
        # TODO: Enable ports 22, 5672, 6379, 11211, 55672, 5000
        pass

    def __try_install_dependencies(self):
        trial = 0
        while trial <= self.NUM_TRIALS:
            if trial == self.NUM_TRIALS:
                raise Exception("Linux Dependency Installation failed after {0} trials!".format(self.NUM_TRIALS))

            print "====================[Trial #{0}]======================".format(trial + 1)

            is_successful = False
            try:
                self.__update_instance()
                self.__install_dependencies()
                is_successful = self.__check_dependency_installation()
            except ShellCommandException:
                pass

            if is_successful:
                print "Trial #{0} of linux dependency installation successful!".format(trial + 1)
                break
            else:
                print "Trial #{0} of linux dependency installation failed!".format(trial + 1)

            time.sleep(5)
            trial += 1

    def __try_install_python_packages(self):
        trial = 0
        while trial <= self.NUM_TRIALS:
            if trial == self.NUM_TRIALS:
                raise Exception("Python package installation failed after {0} trials!".format(self.NUM_TRIALS))

            print "====================[Trial #{0}]======================".format(trial + 1)

            is_successful = False
            try:
                self.__install_python_packages()
                is_successful = self.__check_python_packages_installation()
            except ShellCommandException:
                pass

            if is_successful:
                print "Trial #{0} of python package installation successful!".format(trial + 1)
                break
            else:
                print "Trial #{0} of python package installation failed!".format(trial + 1)

            time.sleep(5)
            trial += 1

    def __is_machine_reachable(self):
        self.__wait_until_successful_ssh()
        print 'Machine with ip: {0} reachable.'.format(self.ip)

    def __update_instance(self):
        header = 'Updating instance...'
        print '=================================================='
        print header
        command = ';'.join(['sudo apt-get -y update',
                            'sudo apt-get -y upgrade',
                            'sudo apt-get -y dist-upgrade'])
        self.__run_remote_command(command=command, log_header=header)

    def __install_dependencies(self):
        header = 'Installing dependencies...'
        print '=================================================='
        print header
        command = "sudo apt-get -y install {0}".format(' '.join(self.dependencies))
        self.__run_remote_command(command=command, log_header=header)

    def __update_fenics(self):
        header = 'Updating FeniCS...'
        print '=================================================='
        print header
        command = ';'.join(['sudo add-apt-repository -y ppa:fenics-packages/fenics',
                            'sudo apt-get -y update',
                            'sudo apt-get -y install fenics',
                            'sudo apt-get -y dist-upgrade'])

        self.__run_remote_command(command=command, log_header=header)


    def __wait_until_successful_ssh(self):
        command = 'echo Machine with ip {0} is up!'.format(self.ip)

        trial = 0
        while trial < self.NUM_SSH_TRIALS:
            time.sleep(5)
            header = 'Trying to ssh into {0} #{1} ...'.format(self.ip, trial + 1)
            if self.verbose:
                print header

            try:
                self.__run_remote_command(command=command, log_header=header)
                print "Machine with ip {0} is up!".format(self.ip)
                break
            except ShellCommandException:
                if self.verbose:
                    print 'SSH failed!'

            except:
                traceback.print_stack()
                break

            trial += 1


    def __reboot_machine(self):
        print '=================================================='
        print 'Rebooting Machine with ip {0}...'.format(self.ip)
        header = 'Trying to reboot {0}'.format(self.ip)

        command = 'sudo reboot'
        if self.verbose:
            print header

        try:
            self.__run_remote_command(command=command, log_header=header)
        except ShellCommandException:
            if self.verbose:
                print 'Reboot via SSH failed!'
        except:
            traceback.print_stack()

        self.__wait_until_successful_ssh()


    def __install_python_packages(self):
        header = 'Installing Python Packages...'
        print '=================================================='
        print header

        commands = []
        for package in self.python_packages:
            if package.has_key('version'):
                commands.append('sudo pip uninstall -y {0}'.format(package['name']))
                commands.append('sudo pip install {0}=={1}'.format(package['name'], package['version']))
            else:
                commands.append('sudo pip install {0}'.format(package['name']))

        command = ';'.join(commands)
        self.__run_remote_command(command=command, log_header=header)


    def __download_stochss_repo(self):
        header = 'Downloading StochSS...'
        print '=================================================='
        print header
        commands = ['rm -rf stochss',
                    'git clone --recursive {0}'.format(self.git_repo['url'])]

        if self.git_repo.has_key('branch'):
            commands.append('cd stochss')
            commands.append('git checkout {0}'.format(self.git_repo['branch']))

        command = ';'.join(commands)
        self.__run_remote_command(command=command, log_header=header)

    def __compile_stochss(self):
        header = 'Compiling StochSS...'
        print '=================================================='
        print header
        commands = ['cd stochss',
                    './run.ubuntu.sh --install']
        command = ';'.join(commands)
        self.__run_remote_command(command=command, log_header=header)

    def run_tests(self):
        # TODO: Add tests for the various job types
        pass

    def __cleanup_instance(self):
        header = 'Cleaning up crumbs...'
        print '=================================================='
        print header
        commands = ['sudo rm -f /etc/ssh/ssh_host_*',
                    'sudo rm -f ~/.ssh/authorized_keys',
                    'sudo rm -f ~/.bash_history']

        command = ';'.join(commands)
        self.__run_remote_command(command=command, log_header=header)


    def __check_dependency_installation(self):
        header = 'Checking dependencies...'
        print '=================================================='
        print header
        expected_dependency_list_string = ' '.join(self.dependencies)
        command = "dpkg-query -W -f='\${Package}\\n' " + expected_dependency_list_string

        tmp_log_files = {
            "stdout": tempfile.TemporaryFile(),
            "stderr": tempfile.TemporaryFile()
        }

        self.__run_remote_command(command=command, log_files=tmp_log_files, silent=True)
        tmp_log_files["stdout"].seek(0)

        dependency_list_string = tmp_log_files["stdout"].read().strip()

        tmp_log_files["stdout"].close()
        tmp_log_files["stderr"].close()

        if sorted(dependency_list_string.split('\n')) == sorted(self.dependencies):
            print 'All dependencies are installed!'
            return True

        else:
            print 'Some dependencies are missing ...'
            print 'List of installed dependencies: \n{0}\n'.format(dependency_list_string)
            return False

    def __check_fenics_installation(self):
        header = 'Checking FeniCS installation...'
        print '=================================================='
        print header

        try:
            self.__run_remote_command(command="python -c 'import dolfin' 2>/dev/null",
                                      log_header=header)
            print 'FeniCS installation successful!'

        except:
            print 'FeniCS installation failed!'


    def __check_python_packages_installation(self):
        header = 'Checking python packages installation...'
        print '=================================================='
        print header
        command = "pip freeze"

        tmp_log_files = {
            "stdout": tempfile.TemporaryFile(),
            "stderr": tempfile.TemporaryFile()
        }

        self.__run_remote_command(command=command, log_files=tmp_log_files, silent=True)
        tmp_log_files["stdout"].seek(0)

        installed_python_packages = {}
        packages = map(lambda x: x.split('=='), tmp_log_files["stdout"].read().split('\n'))
        for package in packages:
            installed_python_packages[package[0].lower()] = package[1] if len(package) == 2 else ""

        tmp_log_files["stdout"].close()
        tmp_log_files["stderr"].close()

        is_successful = True
        for package in self.python_packages:
            if package["name"].lower() not in installed_python_packages.keys():
                is_successful = False
                break
            if "version" in package.keys() and package["version"] != installed_python_packages[package["name"]]:
                is_successful = False
                break

        if is_successful:
            print 'All python packages are installed!'
            return True

        else:
            print 'Some python packages are missing ...'
            print 'List of installed python packages: \n{0}'.format(pprint.pformat(installed_python_packages))
            return False

    def __run_remote_command(self, command, log_header=None, log_files=None, silent=False, timeout=None):
        remote_cmd = get_remote_command(user=self.username, ip=self.ip, key_file=self.keyfile,
                                        command=command)
        if silent == False and self.verbose == True:
            print remote_cmd

        if log_files != None:
            if log_header != None:
                log_files["stdout"].write("LOG_HEADER: {0}\n".format(log_header))
                log_files["stderr"].write("LOG_HEADER: {0}\n".format(log_header))
                log_files["stdout"].flush()
                log_files["stderr"].flush()
            shell_cmd = ShellCommand(remote_cmd, stdout=log_files["stdout"], stderr=log_files["stderr"])

        elif self.log_type == "file":
            if log_header != None:
                self.stdout_log.write("LOG_HEADER: {0}\n".format(log_header))
                self.stderr_log.write("LOG_HEADER: {0}\n".format(log_header))
                self.stdout_log.flush()
                self.stderr_log.flush()
            shell_cmd = ShellCommand(remote_cmd, stdout=self.stdout_log, stderr=self.stderr_log)

        else:
            shell_cmd = ShellCommand(remote_cmd)

        shell_cmd.run(timeout=timeout, silent=silent)


class FlexVMMaker(object):
    def __init__(self, options):
        if 'machine_info' not in options:
            raise Exception('Machine info needed!')

        self.machine_info = options['machine_info']
        settings = options['settings']
        self.dependencies = settings['dependencies']
        self.python_packages = settings['python_packages']
        self.git_repo = settings['git_repo']

        self.keep_existing_stochss_dir = options['keep_existing_stochss_dir']
        self.verbose = options['verbose']

        print 'GIT REPO: {0}'.format(self.git_repo['url'])
        print 'BRANCH: {0}'.format(self.git_repo['branch'])

        if "log" in settings:
            self.log_type = settings["log"]["type"]
        else:
            self.log_type = "screen"

        if self.log_type == "file":
            stdout_log_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), settings["log"]["stdout"])
            print 'stdout_log_filename: {0}'.format(stdout_log_filename)
            self.stdout_log = open(stdout_log_filename, 'w')

            stderr_log_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), settings["log"]["stderr"])
            print 'stderr_log_filename: {0}'.format(stderr_log_filename)
            self.stderr_log = open(stderr_log_filename, 'w')

        else:
            self.stdout_log = None
            self.stderr_log = None


    def __cleanup(self):
        if self.log_type == "file":
            self.stdout_log.close()
            self.stderr_log.close()

    def run(self):
        for machine in self.machine_info:
            ip = machine['ip']
            username = machine['username']
            keyfile = machine['keyfile']

            print '*' * 80
            print 'Running make_flex_vm for:'
            print 'ip: {0}'.format(ip)
            print 'username: {0}'.format(username)
            print 'keyfile: {0}'.format(keyfile)
            print '*' * 80

            if not os.path.exists(keyfile):
                print 'Keyfile: {0} does not exist! Skipping...'.format(keyfile)
                continue

            vm = VirtualMachine(ip=ip, keyfile=keyfile, username=username,
                                dependencies=self.dependencies, python_packages=self.python_packages,
                                git_repo=self.git_repo, keep_existing_stochss_dir=self.keep_existing_stochss_dir,
                                log_type=self.log_type, stdout_log=self.stdout_log, stderr_log=self.stderr_log,
                                verbose=self.verbose)
            vm.make_flex_vm()

        self.__cleanup()
        print 'Done.'


def cleanup_local_files():
    for file in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '*.log')):
        os.remove(file)


def get_arg_parser():
    parser = argparse.ArgumentParser(description="StochSS Flex Cloud VM Maker: \
                                                  Installs packages on the machines, preparing them to be used as Flex \
                                                  Cloud VMs. It takes 10-15 minutes per machine depending \
                                                  on network speed. Use <Ctrl+C> to kill running tool.")
    # parser.add_argument('-m', '--make', help='Make Flex cloud machines', action='store_true')
    parser.add_argument('-f', '--file', help="Machine Configuration File, \
                                              (Default: $STOCHSS/release_tools/flex-cloud/machines.json). \
                                              For more info, visit http://www.stochss.org/",
                        action="store", dest="machine_config_file")
    parser.add_argument('--machine',  nargs=3,metavar=('IP', 'USERNAME', 'KEYFILE'),
                        help='Configuration for one machine, -f option cannot be used along with this option',
                        action='store', dest='machine')
    parser.add_argument('-k', '--keep_existing_stochss_dir', help='Keep existing stochss directory in VM, if any \
                                                                  (Default: False)',
                        action='store_true', dest='keep_existing_stochss_dir', default='False')
    parser.add_argument('-c', '--cleanup', help="Cleanup Local files", action="store_true", default=False)
    parser.add_argument('-v', '--verbose', help="Verbose output", action="store_true")
    parser.add_argument('-s', '--settings', help="Settings File containing package details, git repo, branch, etc. \
                                              (Default: $STOCHSS/release_tools/flex-cloud/settings.json). \
                                              For more info, visit http://www.stochss.org/",
                        action="store", dest="settings_file",
                        default=DEFAULT_SETTINGS_FILE)
    parser.add_argument('-b', '--branch', help="StochSS Git branch name (overridden)", action="store",
                        dest="git_branch")
    return parser


def get_settings(settings_file):
    contents = None
    with open(settings_file) as fin:
        contents = fin.read()
    return json.loads(contents)


def get_flex_vm_maker_options(parsed_args):
    options = {}

    if parsed_args.machine != None and parsed_args.machine_config_file != None:
        raise Exception('Cannot use --machine and -f/--file at the same time!')

    if parsed_args.machine != None:
        if len(parsed_args.machine) != 3:
            raise Exception('Please pass all required arguments for --machine \
                                 option: --machine <ip> <username> <keyfile>')
        options['machine_info'] = [{'ip': parsed_args.machine[0],
                                    'username': parsed_args.machine[1],
                                    'keyfile': parsed_args.machine[2]}]
    else:
        if parsed_args.machine_config_file == None:
            parsed_args.machine_config_file = DEFAULT_MACHINE_CONFIG_FILE

        print 'Machine config file =', parsed_args.machine_config_file
        with open(parsed_args.machine_config_file) as fin:
            contents = fin.read()
        options['machine_info'] = json.loads(contents)

    options['settings'] = get_settings(settings_file=parsed_args.settings_file)
    options['keep_existing_stochss_dir'] = parsed_args.keep_existing_stochss_dir
    options['verbose'] = False if parsed_args.verbose else parsed_args.verbose

    if parsed_args.git_branch != None:
        options['settings']["git_repo"]["branch"] = parsed_args.git_branch

    return options


if __name__ == '__main__':
    parser = get_arg_parser()
    parsed_args = parser.parse_args(sys.argv[1:])

    if parsed_args.cleanup:
        print 'Cleaning up local debris...'
        cleanup_local_files()
    else:
        options = get_flex_vm_maker_options(parsed_args)
        maker = FlexVMMaker(options)
        maker.run()
