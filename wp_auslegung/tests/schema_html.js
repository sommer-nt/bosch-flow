// Erzeugt das Anlagenschema mit schemaSvg() aus index.html für Fälle aus einer JSON-Datei (für test_rechnen.py).
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const block = id => html.match(new RegExp(`<script id="${id}">([\\s\\S]*?)</script>`))[1];
const ctx = {};
vm.createContext(ctx);
vm.runInContext(block('schemasvg') + ';this.schemaSvg=schemaSvg;', ctx);
const faelle = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
process.stdout.write(JSON.stringify(faelle.map(x => ctx.schemaSvg(x.r, x.ie, x.kreise, x.farben, 900))));
