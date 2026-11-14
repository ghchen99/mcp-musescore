const fs = require('fs');
const path = require('path');
// Relative to this script, so it works from any folder.
const code = fs.readFileSync(path.join(__dirname, '..', 'musescore-mcp-websocket.qml'), 'utf8');
// The plugin's functions (from the first "function" up to the onRun handler) are plain JS,
// so they can be parsed on their own without the QML imports and object declarations.
const body = code.slice(code.indexOf('    function '), code.indexOf('    onRun:'));
try {
    new Function(body);
    console.log("No critical syntax errors found by basic JS parser.");
} catch(e) {
    console.log("JS Syntax check:", e);
    process.exit(1);
}
