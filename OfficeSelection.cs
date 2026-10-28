// Read-only queries against an already-running Office-compatible object model.
// No application is created, no Copy/Select/Activate method is called.
using System;using System.Runtime.InteropServices;using Microsoft.Win32;
public static class OfficeSelection {
 public static bool Check(int kind,int length,string document,string window,Func<string> read,Func<string,string> normalize,Func<string,bool> valid) {
  if(kind!=3||length<=0||length>80||String.IsNullOrEmpty(document)||document.Length>512||window.IndexOf(document,StringComparison.OrdinalIgnoreCase)<0)return false;
  string text=read();return text!=null&&text.Length<=80&&valid(normalize(text));
 }
 public static bool Current(string process,string window,Func<string,string> normalize,Func<string,bool> valid) {
  if(process!="wps"&&process!="wpp"&&process!="winword"&&process!="powerpnt")return false;
  foreach(string id in new[]{"KWPP.Application","KWPS.Application","PowerPoint.Application","Word.Application"}) {
   try {
    using(var key=Registry.ClassesRoot.OpenSubKey(id+"\\CLSID")){if(key==null)continue;}
    dynamic app=Marshal.GetActiveObject(id);
    if(id=="KWPP.Application"||id=="PowerPoint.Application") {
     string name=(string)app.ActivePresentation.Name;
     if(window.IndexOf(name,StringComparison.OrdinalIgnoreCase)<0)continue;
     dynamic selection=app.ActiveWindow.Selection;
     if((int)selection.Type!=3)continue;
     dynamic range=selection.TextRange;int length=(int)range.Length;
     if(Check(3,length,name,window,()=>(string)range.Text,normalize,valid))return true;
    } else {
     string name=(string)app.ActiveDocument.Name;
     if(window.IndexOf(name,StringComparison.OrdinalIgnoreCase)<0)continue;
     dynamic range=app.Selection.Range;int length=(int)range.End-(int)range.Start;
     if(Check(3,length,name,window,()=>(string)range.Text,normalize,valid))return true;
    }
   }catch(Exception){} // Unregistered/not-running vendors and unsupported selections.
  }
  return false;
 }
}
