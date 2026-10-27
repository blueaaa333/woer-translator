// Read-only IAccessible2 interop. API specification and BSD notice:
// https://github.com/LinuxA11y/IAccessible2/blob/master/api/AccessibleText.idl
// See licenses/IAccessible2-BSD.txt. No selection or clipboard write is performed.
using System;
using System.Runtime.InteropServices;
using Accessibility;

public interface ISelectedTextReader {
 int Count();
 bool Range(int index,out int start,out int end);
 string Text(int start,int end);
 double[] Bounds(int offset);
}
public static class BrowserTextSelection {
 [StructLayout(LayoutKind.Sequential)]struct Point {public int X,Y;}
 [DllImport("oleacc.dll")]static extern int AccessibleObjectFromPoint(Point point,[MarshalAs(UnmanagedType.Interface)]out IAccessible value,[MarshalAs(UnmanagedType.Struct)]out object child);
 [ComImport,Guid("6D5140C1-7436-11CE-8034-00AA006009FA"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]interface Services {
  [PreserveSig]int QueryService(ref Guid service,ref Guid iid,out IntPtr value);
 }
 [ComImport,Guid("24FD2FFB-3AAD-4A08-8335-A3AD89C0FB4B"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]interface TextApi {
  [PreserveSig]int AddSelection(int start,int end);
  [PreserveSig]int Attributes(int offset,out int start,out int end,[MarshalAs(UnmanagedType.BStr)]out string attributes);
  [PreserveSig]int CaretOffset(out int offset);
  [PreserveSig]int CharacterExtents(int offset,int coordinateType,out int x,out int y,out int width,out int height);
  [PreserveSig]int SelectionCount(out int count);
  [PreserveSig]int OffsetAtPoint(int x,int y,int coordinateType,out int offset);
  [PreserveSig]int Selection(int index,out int start,out int end);
  [PreserveSig]int Text(int start,int end,[MarshalAs(UnmanagedType.BStr)]out string text);
 }
 sealed class Reader:ISelectedTextReader {
  readonly TextApi api;public Reader(TextApi value){api=value;}
  public int Count(){int count;return api.SelectionCount(out count)==0?count:0;}
  public bool Range(int index,out int start,out int end){return api.Selection(index,out start,out end)==0;}
  public string Text(int start,int end){string text;return api.Text(start,end,out text)==0?text:null;}
  public double[] Bounds(int offset){int x,y,w,h;return api.CharacterExtents(offset,0,out x,out y,out w,out h)==0?new double[]{x,y,w,h}:null;}
 }
 public static bool Check(ISelectedTextReader reader,int x,int y,string expected,Func<string,string> normalize,Func<string,bool> valid) {
  for(int i=0,count=Math.Min(8,reader.Count());i<count;i++) {
   int start,end;if(!reader.Range(i,out start,out end)||start<0||end<=start||end-start>80)continue;
   string value=reader.Text(start,end);if(value==null||value.Length>80)continue;
   value=normalize(value);if(!valid(value))continue;
   if(expected!=null){if(String.Equals(value,normalize(expected),StringComparison.OrdinalIgnoreCase))return true;continue;}
   var first=reader.Bounds(start);var last=reader.Bounds(end-1);
   if(first!=null&&last!=null&&Math.Abs(first[1]-last[1])<Math.Max(first[3],last[3])/2) {
    double left=Math.Min(first[0],last[0]),right=Math.Max(first[0]+first[2],last[0]+last[2]);
    if(ToolbarLifecyclePolicy.SelectionNear(new double[]{left,Math.Min(first[1],last[1]),right-left,Math.Max(first[3],last[3])},x,y,true))return true;
   }
   if(ToolbarLifecyclePolicy.SelectionNear(first,x,y,true)||ToolbarLifecyclePolicy.SelectionNear(last,x,y,true))return true;
  }
  return false;
 }
 public static bool AtPoint(int x,int y,string expected,Func<string,string> normalize,Func<string,bool> valid) {
  IAccessible node;object child;
  if(AccessibleObjectFromPoint(new Point{X=x,Y=y},out node,out child)!=0||node==null)return false;
  if(child is int&&(int)child!=0){try{var leaf=node.get_accChild(child) as IAccessible;if(leaf!=null)node=leaf;}catch(COMException){}}
  for(int depth=0;node!=null&&depth<16;depth++) {
   try {
    int state=Convert.ToInt32(node.get_accState(0)),role=Convert.ToInt32(node.get_accRole(0));
    if((state&0x20018000)!=0)return false; // protected, invisible or off-screen
    if(role==1||role==3||role==43||role==51)return false;
    var services=node as Services;
    if(services!=null) {
     var sid=new Guid("618736E0-3C3D-11CF-810C-00AA00389B71");var iid=typeof(TextApi).GUID;IntPtr pointer;
     int hr=services.QueryService(ref sid,ref iid,out pointer);
     if(hr==0&&pointer!=IntPtr.Zero) {
      try{var api=(TextApi)Marshal.GetObjectForIUnknown(pointer);if(Check(new Reader(api),x,y,expected,normalize,valid))return true;}
      finally{Marshal.Release(pointer);}
     }
    }
    if(role==9)break; // never walk out to the desktop
    node=node.accParent as IAccessible;
   }catch(COMException){break;}catch(InvalidCastException){break;}
  }
  return false;
 }
}
