// Prüft alle Schema-Varianten in index.html: kein Text über einer Rohrleitung, kein Text über Text, nichts außerhalb.
// Aufruf: node wp_auslegung/tools/schema_pruefen.js wp_auslegung/index.html
const {chromium}=require('playwright');
const FALL=[
 ['EFH Luft Speicher', {}],
 ['3 Heizkreise gemischt', {heizkreise:[{typ:'hk'},{typ:'fbh'},{typ:'konvektor'}]}],
 ['4 Heizkreise', {heizkreise:[{typ:'hk'},{typ:'fbh'},{typ:'fbh'},{typ:'konvektor'}]}],
 ['Kaskade CS8800', {heizlast:{vorgabe_kw:20}, auswahl:{geraet:'CS8800iAW 13 O-T',anzahl:2,inneneinheit:''}, heizkreise:[{typ:'fbh'},{typ:'fbh'},{typ:'fbh'}]}],
 ['CS5001 MFH', {heizlast:{vorgabe_kw:95}, tww:{personen:40}}],
 ['CS5001 Einzel', {heizlast:{vorgabe_kw:18}, auswahl:{geraet:'CS5001 AW22',anzahl:1,inneneinheit:''}}],
 ['FriWa', {tww:{system:'friwa'}}],
 ['AWMi integriert', {auswahl:{geraet:'CS3800iAW 7 O-S',anzahl:1,inneneinheit:'AWMi'}}],
 ['Puffermodul MB', {auswahl:{geraet:'CS5800/6800iAW 7 OR-S',anzahl:1,inneneinheit:'CS6800iAW 12 MB'}}],
 ['ohne WW', {tww:{aktiv:false}}],
 ['Sole Speicher', {waermequelle:'sole', auslegung:'monovalent'}],
 ['Sole FriWa 2 HK', {waermequelle:'sole', auslegung:'monovalent', tww:{system:'friwa'}, heizkreise:[{typ:'hk'},{typ:'fbh'}]}],
];
(async()=>{
 const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1500,height:1000}});
 await p.goto('file://'+process.argv[2]);
 let fehler=0;
 for(const [name,ae] of FALL){
  const res=await p.evaluate(([ae])=>{
    E=mische(JSON.parse(JSON.stringify(STANDARD)), JSON.parse(JSON.stringify(ae))); aktualisiere();
    const svg=document.querySelector('#schema svg'); if(!svg) return ['kein Schema'];
    const texte=[...svg.querySelectorAll('text')].map(t=>({t:t.textContent,b:t.getBBox()}));
    const rohre=[...svg.querySelectorAll('path.rohr')];
    const out=[];
    const innen=(b,x,y)=>x>b.x-1&&x<b.x+b.width+1&&y>b.y-1&&y<b.y+b.height+1;
    for(const {t,b} of texte){
      for(const r of rohre){const L=r.getTotalLength();for(let l=0;l<=L;l+=1.5){const pt=r.getPointAtLength(l); if(innen(b,pt.x,pt.y)){out.push('Text „'+t+'“ auf Rohr');break;}}}
      if(b.x<0||b.x+b.width>svg.viewBox.baseVal.width+0.5||b.y<0||b.y+b.height>svg.viewBox.baseVal.height+0.5) out.push('Text „'+t+'“ außerhalb');
    }
    for(let i=0;i<texte.length;i++)for(let j=i+1;j<texte.length;j++){const a=texte[i].b,c=texte[j].b;
      if(a.x<c.x+c.width&&c.x<a.x+a.width&&a.y<c.y+c.height&&c.y<a.y+a.height) out.push('Text „'+texte[i].t+'“ über „'+texte[j].t+'“');}
    return [...new Set(out)];
  },[ae]);
  console.log((res.length?'✗ ':'✓ ')+name+(res.length?': '+res.join(' | '):''));
  fehler+=res.length;
  if(process.argv[3]) await p.locator('#schema').screenshot({path:process.argv[3]+'/sch_'+name.replace(/\W+/g,'_')+'.png'});
 }
 console.log('Probleme:',fehler); process.exitCode = fehler ? 1 : 0;
 await b.close();
})();
