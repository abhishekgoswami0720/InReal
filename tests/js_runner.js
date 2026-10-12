// Runs one function from the n8n Code-node sources outside n8n, for tests.
// usage: node tests/js_runner.js file1.js[,file2.js] functionName  < args.json
const fs = require("fs"), path = require("path"), vm = require("vm");
const GLUE = "// ==== n8n glue (below this line runs only inside n8n) ====";
const [files, fn] = process.argv.slice(2);
const src = files.split(",").map(f => fs.readFileSync(path.join(__dirname, "..", "n8n", "code", f), "utf8").split(GLUE)[0]).join("\n");
const ctx = vm.createContext({ URL, console });
vm.runInContext(src + `\n;globalThis.__fn = ${fn};`, ctx);
const args = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(ctx.__fn(...args)));
