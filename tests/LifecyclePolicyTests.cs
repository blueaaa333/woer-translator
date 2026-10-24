using System;
class LifecyclePolicyTests {
 static void Check(bool ok,string name){if(!ok)throw new Exception(name);}
 static void Main(){
  Check(ToolbarLifecyclePolicy.IgnoreMouse(1),"injected mouse ignored");
  Check(!ToolbarLifecyclePolicy.IgnoreMouse(0),"physical mouse retained");
  Check(ToolbarLifecyclePolicy.KeyboardReason(65,0x10,false,false,false)==null,"injected typing cannot close");
  Check(ToolbarLifecyclePolicy.KeyboardReason(27,0x10,false,false,false)==null,"injected Esc cannot close");
  Check(ToolbarLifecyclePolicy.KeyboardReason(45,0,true,false,false)==null,"Ctrl Insert copy does not close");
  Check(ToolbarLifecyclePolicy.KeyboardReason(67,0,true,false,false)==null,"Ctrl C copy does not close");
  Check(ToolbarLifecyclePolicy.KeyboardReason(175,0,false,false,false)==null,"volume key does not close");
  Check(ToolbarLifecyclePolicy.KeyboardReason(27,0,false,false,true)=="escape","physical Esc closes");
  Check(ToolbarLifecyclePolicy.KeyboardReason(37,0,false,false,false)=="navigation","physical arrow closes");
  Check(ToolbarLifecyclePolicy.KeyboardReason(65,0,false,false,false)=="typing","physical typing closes");
  Check(ToolbarLifecyclePolicy.KeyboardReason(65,0,false,false,true)==null,"own controls keep focus");
  Check(ToolbarLifecyclePolicy.IsDoubleClick(false,true,true,120,500,1),"double click opens");
  Check(!ToolbarLifecyclePolicy.IsDoubleClick(false,false,true,120,500,1),"click after drag is cancellation");
  Check(!ToolbarLifecyclePolicy.IsDoubleClick(false,true,false,120,500,1),"other window cannot complete double click");
  Console.WriteLine("PASS 14 input lifecycle checks");
 }
}
