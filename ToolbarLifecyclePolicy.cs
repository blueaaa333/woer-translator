using System;
public static class ToolbarLifecyclePolicy {
 public static bool IsDoubleClick(bool dragged,bool previousClick,bool sameSource,double elapsed,uint threshold,int distance) {
  return !dragged && previousClick && sameSource && elapsed<threshold && distance<8;
 }
 public static bool IgnoreMouse(uint flags) {return (flags&1)!=0;}
 public static string KeyboardReason(int key,uint flags,bool control,bool alt,bool ownWindow) {
  if((flags&0x10)!=0)return null;
  if(key==27)return "escape";
  if(key==9 && alt)return "window_switch";
  if(ownWindow)return null;
  if(control && (key==67||key==45))return null;
  if(key==8 || key==46)return "editing";
  if(key>=33 && key<=40)return "navigation";
  if(key==9 || key==13 || key==32 || (key>=48&&key<=90) || (key>=96&&key<=111) || (key>=186&&key<=222))return "typing";
  return null;
 }
}
