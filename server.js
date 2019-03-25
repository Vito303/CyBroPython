const express = require('express')
const app = express()

//http://localhost:4000/get?tag=tagname
app.get('/get', (req, res) => {
    //console.log(req.query.tag);
    let tag = req.query.tag; 
    const { spawn } = require('child_process');
    const pyProg = spawn('python', ['./CyBroScgiServer/src/CyBroGetSet.py', tag]);
    
    pyProg.stdout.on('data', function(data) {
        console.log(data.toString());
        res.write(data);
        res.end();
    });
})

//http://localhost:4000/set?tag=tagname&value=1
app.get('/set', (req, res) => {
    //console.log(req.query.tag);
    //console.log(req.query.value);
    let tag = req.query.tag;
    let tagValue = req.query.value;
    const { spawn } = require('child_process');
    const pyProg = spawn('python', ['./CyBroScgiServer/src/CyBroGetSet.py', tag, '--value', tagValue]);

    pyProg.stdout.on('data', function(data) {
        console.log(data.toString());
        res.write(data);
        res.end();
    });
})


app.listen(4000, () => console.log('Application listening on port 4000!'))

// Run with: node --inspect=0.0.0.0:9229 server.js