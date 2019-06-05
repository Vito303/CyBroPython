var zerorpc = require("zerorpc");

var server = new zerorpc.Server({
    PushRequest: function(name, reply) {
        console.log(name.toString("utf8"));
        reply(null, "Response: " + name);
    },
    ServerShutdownRequest: function(reply) {
        reply(null, "true");
        //reply(null, "false");
    }
});


server.bind("tcp://0.0.0.0:4242");
console.log("Server started.");