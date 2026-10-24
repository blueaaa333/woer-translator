const {test}=require('node:test');const assert=require('node:assert/strict');
const {assetName,checksum,download}=require('./cli.cjs');
test('selects real platform installers',()=>{
 assert.match(assetName('win32','x64'),/Windows-x64-Setup.exe$/);
 assert.match(assetName('darwin','arm64'),/macOS-arm64.dmg$/);
 assert.match(assetName('darwin','x64'),/macOS-x64.dmg$/);
 assert.throws(()=>assetName('linux','x64'));
});
test('checksum must match exact filename',()=>{
 const hash='a'.repeat(64);assert.equal(checksum(hash+'  app.dmg\n','app.dmg'),hash);
 assert.throws(()=>checksum(hash+'  other.dmg','app.dmg'));
});
test('mismatch refuses saving or opening',async()=>{
 let calls=0;
 const request=async()=>++calls===1?{ok:true,text:async()=> 'a'.repeat(64)+'  app.dmg'}:{ok:true,arrayBuffer:async()=>Buffer.from('bad')};
 await assert.rejects(download('app.dmg','unused',request),/SHA256 verification failed/);
 await assert.rejects(download('../app.dmg','unused',request),/filename/);
});
