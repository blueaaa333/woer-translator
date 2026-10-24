#!/usr/bin/env node
'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const VERSION=require('./package.json').version;
function assetName(platform,arch){
  if(platform==='win32'&&arch==='x64')return `WoerTranslator-${VERSION}-Windows-x64-Setup.exe`;
  if(platform==='darwin'&&['arm64','x64'].includes(arch))return `WoerTranslator-${VERSION}-macOS-${arch}.dmg`;
  throw new Error('Supported platforms: Windows x64, macOS arm64 / x64.');
}
function checksum(text,name){
  const line=text.split(/\r?\n/).find(line=>line.slice(66).replace(/^\*/, '')===name);
  if(!line||!/^([a-f0-9]{64}) [ *]/.test(line))throw new Error('No trusted checksum for '+name);
  return line.slice(0,64);
}
async function download(name,directory,request=fetch){
  if(path.basename(name)!==name)throw new Error('Invalid asset filename');
  const base=`https://github.com/blueaaa333/woer-translator/releases/download/v${VERSION}/`;
  const sums=await request(base+'SHA256SUMS.txt');
  if(!sums.ok)throw new Error('Cannot download checksums: HTTP '+sums.status);
  const expected=checksum(await sums.text(),name);
  const response=await request(base+name);
  if(!response.ok)throw new Error('Cannot download installer: HTTP '+response.status);
  const bytes=Buffer.from(await response.arrayBuffer());
  if(crypto.createHash('sha256').update(bytes).digest('hex')!==expected)throw new Error('SHA256 verification failed; installer was not saved or opened.');
  await fs.mkdir(directory,{recursive:true});const target=path.resolve(directory,name);
  await fs.writeFile(target,bytes,{flag:'wx'});return target;
}
async function main(argv=process.argv.slice(2)){
  const action=argv[0];
  if(!['download','install'].includes(action)){
    console.log('Woer Translator '+VERSION+'\nUsage: woer-translator download [directory]\n       woer-translator install [directory]\nDownload verifies SHA256. Install opens the OS installer after verification.');return;
  }
  const target=await download(assetName(process.platform,process.arch),argv[1]||process.cwd());
  console.log('Verified installer: '+target);
  if(action==='install'){
    const child=process.platform==='darwin'?spawn('/usr/bin/open',[target],{stdio:'inherit'}):spawn(target,[],{stdio:'inherit'});
    await new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(new Error('Installer exited: '+code)));});
  }
}
module.exports={assetName,checksum,download,main};
if(require.main===module)main().catch(error=>{console.error(error.message);process.exitCode=1;});
