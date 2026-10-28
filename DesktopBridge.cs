using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Automation;
using System.Windows.Forms;

// Hook callbacks only record events. Accessibility calls run in a disposable process.
class DesktopBridge {
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X,Y; }
 [StructLayout(LayoutKind.Sequential)] struct MOUSE { public POINT pt; public uint mouseData,flags,time; public IntPtr extra; }
 delegate IntPtr MouseProc(int n,IntPtr w,IntPtr l);
 delegate IntPtr KeyProc(int n,IntPtr w,IntPtr l);
 static MouseProc mouseProc=Mouse;
 static KeyProc keyProc=Keyboard;
 static IntPtr hook=IntPtr.Zero;
 static IntPtr keyHook=IntPtr.Zero;
 static uint sourceClipboard;static POINT start,last;static DateTime release=DateTime.MinValue;
 static bool lastWasClick;static IntPtr lastSource=IntPtr.Zero;
 static IntPtr source=IntPtr.Zero; static uint sourcePid;static int sequence;static string pending,clearPending;
 static System.Windows.Forms.Timer debounce;static int parent;static string copyPending,warmPending;
 [DllImport("user32.dll")]static extern uint GetClipboardSequenceNumber();
 [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int id,MouseProc cb,IntPtr module,uint tid);
 [DllImport("user32.dll",EntryPoint="SetWindowsHookExA")] static extern IntPtr SetKeyHook(int id,KeyProc cb,IntPtr module,uint tid);
 [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr h);
 [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr h,int n,IntPtr w,IntPtr l);
 [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(POINT point);
 [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr window,uint flags);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
 [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT p);
 [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
 [DllImport("kernel32.dll",CharSet=CharSet.Auto)] static extern IntPtr GetModuleHandle(string name);
 [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr context);
 [DllImport("user32.dll")] static extern uint GetDoubleClickTime();
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern int GetWindowTextW(IntPtr hwnd,StringBuilder text,int size);
 static void Cancel(string reason,uint pid) {
  long when=(long)(DateTime.UtcNow-new DateTime(1970,1,1)).TotalMilliseconds;
  clearPending="CLEAR|"+reason+"|"+when+"|"+pid;
 }
 static IntPtr Mouse(int n,IntPtr w,IntPtr l) {
  if(n>=0) {
   var m=(MOUSE)Marshal.PtrToStructure(l,typeof(MOUSE));int message=w.ToInt32();
   if(ToolbarLifecyclePolicy.IgnoreMouse(m.flags))return CallNextHookEx(hook,n,w,l);
   if(message==0x201){sourceClipboard=GetClipboardSequenceNumber();start=m.pt;source=GetAncestor(WindowFromPoint(m.pt),2);GetWindowThreadProcessId(source,out sourcePid);
    if(sourcePid!=parent)Cancel("pointer_down",sourcePid);
    if(sourcePid!=parent)warmPending="WARM|"+sourcePid+"|"+source.ToInt64()+"|"+m.pt.X+"|"+m.pt.Y+"|"+(long)(DateTime.UtcNow-new DateTime(1970,1,1)).TotalMilliseconds;
   }
   if(message==0x205){uint target;GetWindowThreadProcessId(WindowFromPoint(m.pt),out target);if(target!=parent)Cancel("context_menu",target);}
   if(message==0x202) {
    var now=DateTime.UtcNow;
    bool dragged=Math.Abs(m.pt.X-start.X)+Math.Abs(m.pt.Y-start.Y)>4;
    bool doubled=ToolbarLifecyclePolicy.IsDoubleClick(dragged,lastWasClick,source==lastSource,(now-release).TotalMilliseconds,GetDoubleClickTime(),Math.Abs(m.pt.X-last.X)+Math.Abs(m.pt.Y-last.Y));
    release=now;last=m.pt;lastSource=source;lastWasClick=!dragged&&!doubled;
    if((dragged||doubled) && sourcePid!=parent && source!=IntPtr.Zero){
     long nowMs=(long)(now-new DateTime(1970,1,1)).TotalMilliseconds;
     pending=sourcePid+"|"+source.ToInt64()+"|"+m.pt.X+"|"+m.pt.Y+"|"+(++sequence)+"|"+nowMs+"|"+sourceClipboard;
    }
    else if(!dragged && !doubled && sourcePid!=parent){pending=null;Cancel("click",sourcePid);}
   }
  }
  return CallNextHookEx(hook,n,w,l);
 }
 static IntPtr Keyboard(int n,IntPtr w,IntPtr l) {
  if(n>=0 && (w.ToInt32()==0x100 || w.ToInt32()==0x104)) {
   int key=Marshal.ReadInt32(l);uint flags=unchecked((uint)Marshal.ReadInt32(l,8));
   if((flags&0x10)!=0)return CallNextHookEx(keyHook,n,w,l);
   uint pid;IntPtr foreground=GetForegroundWindow();GetWindowThreadProcessId(foreground,out pid);
   bool control=(GetAsyncKeyState(17)&0x8000)!=0;
   if(control&&(key==67||key==45)&&pid!=parent) {
    long at=(long)(DateTime.UtcNow-new DateTime(1970,1,1)).TotalMilliseconds;
    copyPending="COPY|"+pid+"|"+foreground.ToInt64()+"|"+GetClipboardSequenceNumber()+"|"+at;
   }
   string reason=ToolbarLifecyclePolicy.KeyboardReason(key,flags,(GetAsyncKeyState(17)&0x8000)!=0,(GetAsyncKeyState(18)&0x8000)!=0,pid==parent);
   if(reason!=null){pending=null;Cancel(reason,pid);}
  }
  return CallNextHookEx(keyHook,n,w,l);
 }
 static string Selection(uint pid,IntPtr hwnd,int x,int y) {
  uint actual;GetWindowThreadProcessId(hwnd,out actual);if(actual!=pid)return "";
  var element=AutomationElement.FromPoint(new System.Windows.Point(x,y));
  string text="";
  if(element!=null && element.Current.ProcessId==pid)text=Read(element);
  if(text.Length>0)return text;
  var root=AutomationElement.FromHandle(hwnd);
  text=Read(root);if(text.Length>0)return text;
  // Browser text lives in its document provider, not necessarily the focused element.
  var document=root.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document));
  return document==null?"":Read(document);
 }
 static string rangeStatus="no_text_provider";
 static bool CheckSelectedRange(AutomationElement element,int x,int y,string expected) {
  if(element==null)return false;
  try {
   if(element.Current.IsPassword)return false;
   object pattern;if(!element.TryGetCurrentPattern(TextPattern.Pattern,out pattern))return false;
   foreach(var range in ((TextPattern)pattern).GetSelection()) {
    bool nonempty=range.CompareEndpoints(System.Windows.Automation.Text.TextPatternRangeEndpoint.Start,range,System.Windows.Automation.Text.TextPatternRangeEndpoint.End)!=0;
    if(!nonempty){rangeStatus="collapsed";continue;}
    string text=NormalizeQuery(range.GetText(81));if(!ValidQuery(text)){rangeStatus="unsupported_text";continue;}
    rangeStatus="range_outside_pointer";
    if(expected!=null) {if(String.Equals(text,NormalizeQuery(expected),StringComparison.OrdinalIgnoreCase))return true;}
    else foreach(var rect in range.GetBoundingRectangles())if(ToolbarLifecyclePolicy.SelectionNear(new double[]{rect.X,rect.Y,rect.Width,rect.Height},x,y,true))return true;
   }
  }catch(ElementNotAvailableException){}catch(InvalidOperationException){}catch(COMException){}
  return false;
 }
 static bool CheckSelectionAncestors(AutomationElement element,IntPtr hwnd,int x,int y,string expected) {
  // PDF text leaves and the document provider can be separated by raw wrappers.
  for(int depth=0;element!=null&&depth<16;depth++) {
   if(CheckSelectedRange(element,x,y,expected))return true;
   try {if(element.Current.IsPassword)return false;if(element.Current.NativeWindowHandle==hwnd.ToInt64())break;element=TreeWalker.RawViewWalker.GetParent(element);}
   catch(ElementNotAvailableException){break;}catch(COMException){break;}
  }
  return false;
 }
 static string verifyReason="starting";
 static bool SelectionReady(uint pid,IntPtr hwnd,int x,int y,string expected) {
  verifyReason="foreground_changed";
  rangeStatus="no_text_provider";
  if(GetForegroundWindow()!=hwnd)return false;
  uint actual;GetWindowThreadProcessId(hwnd,out actual);if(actual!=pid)return false;
  bool copying=expected!=null;
  if(!copying) {
   verifyReason="office_readonly";var title=new StringBuilder(1024);GetWindowTextW(hwnd,title,title.Capacity);
   if(OfficeSelection.Current(Process.GetProcessById((int)pid).ProcessName.ToLowerInvariant(),title.ToString(),NormalizeQuery,ValidQuery))return GetForegroundWindow()==hwnd;
  }
  verifyReason="pointer_covered";
  if(!copying&&GetAncestor(WindowFromPoint(new POINT{X=x,Y=y}),2)!=hwnd)return false;
  verifyReason="uia_point";
  var root=AutomationElement.FromHandle(hwnd);
  AutomationElement element=copying?AutomationElement.FocusedElement:AutomationElement.FromPoint(new System.Windows.Point(x,y));
  if(element!=null) {
   if(element.Current.IsPassword)return false;
   var role=element.Current.ControlType;
   if(!copying&&(role==ControlType.ScrollBar||role==ControlType.Thumb||role==ControlType.Button||role==ControlType.Slider||role==ControlType.TitleBar))return false;
   if(CheckSelectionAncestors(element,hwnd,x,y,expected))return GetForegroundWindow()==hwnd;
  }
  // Chromium/PDF can expose IA2 text selection even when its UIA bridge has no range.
  verifyReason="ia2";
  try{if(BrowserTextSelection.AtPoint(x,y,expected,NormalizeQuery,ValidQuery))return GetForegroundWindow()==hwnd;}catch(COMException){}
  // Chromium's PDF document is sometimes a sibling of the hit-tested surface,
  // so walking only upward from the mouse cannot reach its TextPattern.
  verifyReason="uia_documents";
  var documents=root.FindAll(TreeScope.Descendants,new OrCondition(new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document),new PropertyCondition(AutomationElement.IsTextPatternAvailableProperty,true)));
  int inspected=0;
  for(int i=0;i<documents.Count&&i<512&&inspected<24;i++) {
   var document=documents[i];
   if(document.Current.IsOffscreen)continue;
   if(!copying&&!document.Current.BoundingRectangle.Contains(new System.Windows.Point(x,y)))continue;
   inspected++;
   if(CheckSelectedRange(document,x,y,expected))return GetForegroundWindow()==hwnd;
  }
  verifyReason="no_accessible_selection/"+documents.Count+"/"+inspected+"/"+rangeStatus;return false;
 }
 static void WarmSelectionProvider(uint pid,IntPtr hwnd,int x,int y) {
  if(GetForegroundWindow()!=hwnd)return;
  uint actual;GetWindowThreadProcessId(hwnd,out actual);if(actual!=pid)return;
  var element=AutomationElement.FromPoint(new System.Windows.Point(x,y));
  for(int i=0;element!=null&&i<3;i++) {
   if(element.Current.IsPassword)return;
   object pattern;if(element.TryGetCurrentPattern(TextPattern.Pattern,out pattern))return;
   element=TreeWalker.RawViewWalker.GetParent(element);
  }
 }
 static void VerifyServer(int owner) {
  using(var life=new System.Threading.Timer(_=>{try{if(Process.GetProcessById(owner).HasExited)Environment.Exit(0);}catch{Environment.Exit(0);}},null,1000,1000)) {
   var thread=new System.Threading.Thread(()=>{
    try{AutomationElement.RootElement.GetRuntimeId();}catch{}
    Console.WriteLine("READY");Console.Out.Flush();string line;
    while((line=Console.ReadLine())!=null) {
     bool selected=false;
     try{var f=line.Split('|');string expected=f.Length>4&&!String.IsNullOrEmpty(f[4])?Encoding.UTF8.GetString(Convert.FromBase64String(f[4])):null;
      if(f.Length>5&&f[5]=="W") {
       WarmSelectionProvider(uint.Parse(f[0]),new IntPtr(long.Parse(f[1])),int.Parse(f[2]),int.Parse(f[3]));
       Console.WriteLine("EMPTY|warm_ready");Console.Out.Flush();continue;
      }
      selected=SelectionReady(uint.Parse(f[0]),new IntPtr(long.Parse(f[1])),int.Parse(f[2]),int.Parse(f[3]),expected);
      if(!selected){System.Threading.Thread.Sleep(75);selected=SelectionReady(uint.Parse(f[0]),new IntPtr(long.Parse(f[1])),int.Parse(f[2]),int.Parse(f[3]),expected);}
     }catch(Exception error){verifyReason=error.GetType().Name;}
     Console.WriteLine((selected?"SELECTED":"EMPTY")+"|"+verifyReason);Console.Out.Flush();
    }
   });thread.IsBackground=true;thread.SetApartmentState(System.Threading.ApartmentState.MTA);thread.Start();thread.Join();
  }
 }
 static void Serve() {
  Console.WriteLine("READY");Console.Out.Flush();string request;
  while((request=Console.ReadLine())!=null) {
   var f=request.Split('|');string text="",status="empty";
   try {text=Selection(uint.Parse(f[0]),new IntPtr(long.Parse(f[1])),int.Parse(f[2]),int.Parse(f[3]));status=text.Length>0?"ok":"empty";}catch{status="unavailable";}
   Console.WriteLine(f[4]+"|"+status+"|"+Convert.ToBase64String(Encoding.UTF8.GetBytes(text)));Console.Out.Flush();
  }
 }
 static string Read(AutomationElement e) {
  for(int depth=0;e!=null && depth<4;depth++) {
   object p;
   if(e.TryGetCurrentPattern(TextPattern.Pattern,out p)) {
    var ranges=((TextPattern)p).GetSelection();
    if(ranges.Length>0) {
     string text=NormalizeQuery(ranges[0].GetText(81));
     if(ValidQuery(text))return text;
    }
   }
   e=TreeWalker.ControlViewWalker.GetParent(e);
  }
  return "";
 }
 static string NormalizeQuery(string text) {
  text=text.Replace("\u00ad","");
  text=Regex.Replace(text,"[\u2010\u2011\u2012\u2013\u2014\u2212\ufe63\uff0d]","-");
  text=Regex.Replace(text,"[\u2018\u2019\u02bc]","'");
  text=Regex.Replace(text,@"\s*-\s*","-");
  text=Regex.Replace(text,@"\s+"," ").Trim().Trim(',',';',':','!','?','“','”','"','(',')','[',']');
  return text.TrimEnd('.').Contains(".")?text:text.Trim('.');
 }
 static bool ValidQuery(string text) {
  return text.Length<=80 && text.Split(' ').Length<=6 && Regex.IsMatch(text,@"^[A-Za-z]+(?:[-'. ][A-Za-z]+)*\.?$");
 }
 static void Watch(int parentId) {
  parent=parentId;
  debounce=new System.Windows.Forms.Timer();debounce.Interval=16;
  debounce.Tick+=(s,e)=>{string warm=warmPending;warmPending=null;if(warm!=null)Console.WriteLine(warm);string copy=copyPending;copyPending=null;if(copy!=null)Console.WriteLine(copy);string clear=clearPending;clearPending=null;string message=pending;pending=null;if(clear!=null)Console.WriteLine(clear);if(message!=null)Console.WriteLine(message);if(warm!=null||copy!=null||clear!=null||message!=null)Console.Out.Flush();};debounce.Start();
  var life=new System.Windows.Forms.Timer();life.Interval=1500;
  life.Tick+=(s,e)=>{try {if(Process.GetProcessById(parent).HasExited)Application.Exit();}catch{Application.Exit();}};life.Start();
  hook=SetWindowsHookEx(14,mouseProc,GetModuleHandle(null),0);
  keyHook=SetKeyHook(13,keyProc,GetModuleHandle(null),0);
  if(hook==IntPtr.Zero){Console.Error.WriteLine("MOUSE_HOOK_FAILED");Environment.Exit(3);}
  Console.WriteLine("READY");Console.Out.Flush();
  try {Application.Run();}finally{UnhookWindowsHookEx(hook);if(keyHook!=IntPtr.Zero)UnhookWindowsHookEx(keyHook);}
 }
 static int Speak(string accent,string word,bool list) {
  Type type=Type.GetTypeFromProgID("SAPI.SpVoice");dynamic voice=Activator.CreateInstance(type);dynamic tokens=voice.GetVoices();
  string wanted=accent=="1"?"809":"409";dynamic chosen=null;
  for(int i=0;i<tokens.Count;i++) {
   dynamic token=tokens.Item(i);string lang=token.GetAttribute("Language");
   if(list)Console.WriteLine(lang+"|"+token.GetDescription());
   else if(Array.Exists(lang.Split(';'),v=>v.Equals(wanted,StringComparison.OrdinalIgnoreCase)))chosen=token;
  }
  if(list)return 0;
  if(chosen==null){Console.WriteLine("MISSING_VOICE");return 4;}
  voice.Voice=chosen;voice.Rate=-1;voice.Speak(word,0);return 0;
 }
 [STAThread] static int Main(string[] args) {
  try {SetProcessDpiAwarenessContext(new IntPtr(-4));}catch(EntryPointNotFoundException){}
  Console.OutputEncoding=new UTF8Encoding(false);
  try {
   if(args[0]=="verify-server"){VerifyServer(int.Parse(args[1]));return 0;}
   if(args[0]=="watch") {Watch(int.Parse(args[1]));return 0;}
   if(args[0]=="verify") {
    var deadline=new System.Threading.Thread(()=>{System.Threading.Thread.Sleep(1200);Environment.Exit(4);});deadline.IsBackground=true;deadline.Start();
    string line=Console.ReadLine();string expected=String.IsNullOrEmpty(line)?null:Encoding.UTF8.GetString(Convert.FromBase64String(line));
    bool selected=false;
    var verifyThread=new System.Threading.Thread(()=>{try{selected=SelectionReady(uint.Parse(args[1]),new IntPtr(long.Parse(args[2])),int.Parse(args[3]),int.Parse(args[4]),expected);}catch{selected=false;}});
    verifyThread.IsBackground=true;verifyThread.SetApartmentState(System.Threading.ApartmentState.MTA);verifyThread.Start();
    bool completed=verifyThread.Join(420);
    Console.WriteLine(completed&&selected?"SELECTED":"EMPTY");return 0;
   }
   if(args[0]=="serve") {Serve();return 0;}
   if(args[0]=="select") {
    uint pid;GetWindowThreadProcessId(GetForegroundWindow(),out pid);
    if(pid!=uint.Parse(args[1]))return 0;
    string text=Read(AutomationElement.FromPoint(new System.Windows.Point(int.Parse(args[2]),int.Parse(args[3]))));
    if(text.Length==0)text=Read(AutomationElement.FocusedElement);
    Console.WriteLine(text);return 0;
   }
   if(args[0]=="voices")return Speak("","",true);
   if(args[0]=="speak" && ValidQuery(NormalizeQuery(args[2])))return Speak(args[1],NormalizeQuery(args[2]),false);
  } catch(Exception ex) {Console.Error.WriteLine(ex.GetType().Name);return 2;}
  return 1;
 }
}
