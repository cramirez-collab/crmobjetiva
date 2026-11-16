import { readFileSync, writeFileSync } from 'fs';
import { LibreDwg } from '@mlightcad/libredwg-web';
const lib = await LibreDwg.create();
for (let i=2;i<process.argv.length;i+=2){
  const src=process.argv[i], dst=process.argv[i+1];
  try{ const buf=readFileSync(src); const out=lib.dwg_write_dxf(buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength));
    if(!out){console.log('FAIL',src);continue;} writeFileSync(dst,out); console.log('OK',dst,out.length);}catch(e){console.log('ERR',src,e.message)}
}
