// Führt den Rechenkern aus index.html mit den Daten aus index.html für alle Szenarien aus (für test_rechnen.py).
// Aufruf: node rechne_html.js index.html szenarien.json  -> JSON auf stdout
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const block = id => html.match(new RegExp(`<script id="${id}">([\\s\\S]*?)</script>`))[1];
const ctx = {module: undefined};
vm.createContext(ctx);
vm.runInContext(block('daten') + ';this.GERAETE_DATEN=GERAETE_DATEN;this.KATALOG_DATEN=KATALOG_DATEN;', ctx);
vm.runInContext(block('rechenkern') + ';this.RK=RK;', ctx);
const sz = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = sz.map(s => ctx.RK.rechne(s.eingaben, ctx.GERAETE_DATEN, ctx.KATALOG_DATEN));
process.stdout.write(JSON.stringify(out));
