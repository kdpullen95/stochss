if (typeof(String.prototype.trim) === "undefined") {
    String.prototype.trim = function () {
        return String(this).replace(/^\s+|\s+$/g, '');
    };
}

function get_cluster_info_input() {
    var cluster_node_info = [];
    var cluster_node = {};

    var tbody = $('#cluster_info_table');
    var rows = tbody.find('tr');
    for (i = 0; i < rows.length; i++) {
        var row = $(rows[i]);
        cluster_node = {};

        try {
            cluster_node['ip'] = row.find('input[name="ip"]').val().trim();
            // if (cluster_node['ip'] == '') {
            //     updateMsg({ status: false, msg: 'Please provide valid IP Address!' }, '#clusterInfoMsg');
            //     return null
            // }

            cluster_node['username'] = row.find('input[name="username"]').val().trim();
            // if (cluster_node['username'] == '') {
            //     updateMsg({ status: false, msg: 'Please provide valid username!' }, '#clusterInfoMsg');
            //     return null
            // }

            cluster_node['key_file_id'] = parseInt(row.find('select').val());
            // if (!cluster_node['key_file_id']) {
            //     updateMsg({ status: false, msg: 'Please select a key file' }, '#clusterInfoMsg');
            //     return null;
            // }
        }
        catch (err){
        }
        cluster_node_info.push(cluster_node);
    }

    return cluster_node_info
}

function save_cluster_info() {
    var cluster_info = get_cluster_info_input();
    if (cluster_info == null) {
        updateMsg( { status : false, msg : "Changes unsuccessful." }, '#clusterInfoMsg');
        return;
    }

    var jsonDataToBeSent = {};
    jsonDataToBeSent['cluster_info'] = cluster_info;

    jsonDataToBeSent = JSON.stringify(jsonDataToBeSent);
    updateMsg( { status : true, msg : "Saving information..." }, '#clusterInfoMsg');
    $.ajax({
        type: "POST",
        url: "/clusterCredentials",
        contentType: "application/json",
        dataType: "json",
        data: jsonDataToBeSent,
        success: function () {
        },
        error: function (x, e) {
        },
        complete: function () {
            document.location.reload();
        }
    });
}

$(document).ready(function () {
    $("#append_cluster_node").click(function () {

        var prior_row = $('#cluster_info_table tr:last');

        var new_row = prior_row.clone(true);
        new_row.find('input[name="ip"]').val("");
        new_row.find('input[name="username"]').val("");
        new_row.find('select').val(prior_row.find('select').val());
        prior_row.after(new_row);
        return false;
    });

    // $("#delete_cluster_node").click(function () {
    //     if ($('#cluster_info_table tr').length == 1) {
    //         $('#cluster_info_table tr:last').find('input').val("");
    //     }
    //     else {
    //         var rowCount = $('#cluster_info_table tr').length;
    //         $('#cluster_info_table tr').eq(rowCount - 2).remove();
    //     }
    //     return false;
    // });
});

var Cluster = Cluster || {}

var updateMsg = function (data, msg) {
    if (!_.has(data, 'status')) {
        $(msg).text('').prop('class', '');

        return;
    }

    var text = data.msg;

    if (typeof text != 'string') {
        text = text.join('<br>')
    }

    $(msg).html(text);
    if (data.status)
        $(msg).prop('class', 'alert alert-success');
    else
        $(msg).prop('class', 'alert alert-error');
    $(msg).show();
};



Cluster.Controller = Backbone.View.extend({
    el: $("#cluster"),

    initialize: function (attributes) {
        this.attributes = attributes;
        this.clusterKeyFiles = undefined;

        //this.flexIsRunning = $( "#prepare_flex_button" ).prop('disabled');

        this.loaded = 0;

        this.clusterKeyFiles = new fileserver.FileList([], { key: 'clusterKeyFiles' });
        this.clusterKeyFiles.fetch({ success: _.bind(_.partial(this.update_loaded, undefined), this) });
    },

    update_loaded: function (data) {
        if ($.isReady) {
            this.render();
        }
    },

    render: function () {
        $(this.el).find("cluster_ssh_key_table").empty();

        $(this.el).find('#keyfile_to_upload').fileupload({
            url: '/FileServer/large/clusterKeyFiles',
            dataType: 'json',

            add: _.partial(function (controller, e, data) {
                var inUse = false;

                for (var i = 0; i < controller.clusterKeyFiles.models.length; i++) {
                    if (controller.clusterKeyFiles.models[i].attributes.path == data.files[0].name) {
                        inUse = true;
                        break;
                    }
                }

                if (!inUse) {
                    if (data.autoUpload || (data.autoUpload !== false && $(this).fileupload('option', 'autoUpload'))) {
                        data.process().done(function () {
                            updateMsg({ status: true, msg: 'Uploading private key...' }, '#clusterKeyMsg');
                            data.submit();
                        });
                    }
                }
                else {
                    updateMsg({ status: false,
                                msg: "Key with name '" + data.files[0].name + "' already exists" },
                        "#clusterKeyMsg");
                    return false;
                }
            }, this),

            done: _.bind(function (e, data) {
                updateMsg({ status: true, msg: 'Key uploaded. Page reloading' }, '#clusterKeyMsg');
                location.reload();
            }, this),

            error: function (data) {
                updateMsg({ status: false,
                    msg: "Server error uploading file" }, "#csvMsg");
            }
        }).prop('disabled', !$.support.fileInput)
            .parent().addClass($.support.fileInput ? undefined : 'disabled');

        this.renderFiles();

    },

    deleteKeyFile: function (clusterKeyFileId, event) {
        var result = confirm("Are you sure you want to delete this key?");

        if (result) {
            var clusterKeyFile = this.clusterKeyFiles.get(clusterKeyFileId);

            updateMsg({ status: true, msg: "Key '" + clusterKeyFile.attributes.path + "' deleted" }, "#clusterKeyMsg");

            $(this.el).find('option[value="' + clusterKeyFile.attributes.id + '"]').remove();

            clusterKeyFile.destroy();
            this.renderFiles();
        }

        event.preventDefault();
    },

    renderFiles: function () {
        $(this.el).find('#progresses').empty();
        $(this.el).find("#cluster_ssh_key_table").empty();

        if (typeof this.clusterKeyFiles != 'undefined') {
            var row_template = _.template("<tr> \
<td> \
<%= keyname %> \
</td> \
<td width='100px'> \
<% if(is_deletable) { %> \
<button><i class='icon-trash'></i> Delete</button> \
<% } else { %> \
In Use \
<% } %> \
</td> \
</tr>");

            if(this.clusterKeyFiles.length > 0)
            {
                for (var i = 0; i < this.clusterKeyFiles.models.length; i++) {
                    var keyFile = this.clusterKeyFiles.models[i];

                    var keyRow = $(row_template({ keyname: keyFile.attributes.path, is_deletable: true})).appendTo("#cluster_ssh_key_table"); // true was initially !this.flexIsRunning

                    if (keyRow.find('button').length) {
                        var button = keyRow.find('button');

                        button.click(_.bind(_.partial(this.deleteKeyFile, keyFile.id), this));
                    }
                }

                $( "#cluster_ssh_key_table_div" ).show();
                $( "#cluster_ssh_key_table_div_loading" ).hide();
            }
            else
            {
                $( "#cluster_ssh_key_table_div" ).hide();
                $( "#cluster_ssh_key_table_div_loading" ).hide();
            }
        }
    }
});

var cont = new Cluster.Controller();

window.onload = function () {
    $('#cluster_ssh_key_table_table').DataTable({ "bSort": false, "bLengthChange": false, "bFilter": false, "bPaginate": false, "bInfo": false });
    $('#cluster_ssh_key_table_table').css('border-bottom', '1px solid #ddd');
    $('#cluster_ssh_key_table_table thead th').css('border-bottom', '1px solid #ddd');
    $( '#submit_info_button' ).click( save_cluster_info );

    cont.render();
};
