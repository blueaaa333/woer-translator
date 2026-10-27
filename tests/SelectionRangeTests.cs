using System;
class SelectionRangeTests {
 static void Check(bool value,string label){if(!value)throw new Exception(label);}
 static void Main(){
  var box=new double[]{100,100,60,18};
  Check(!ToolbarLifecyclePolicy.SelectionNear(box,120,110,false),"collapsed range");
  Check(!ToolbarLifecyclePolicy.SelectionNear(new double[]{100,100,0,18},100,100,true),"zero width");
  Check(!ToolbarLifecyclePolicy.SelectionNear(box,400,400,true),"unrelated stale selection");
  Check(ToolbarLifecyclePolicy.SelectionNear(box,164,110,true),"release at selection edge");
  Check(!ToolbarLifecyclePolicy.SelectionNear(new double[]{0,0,Double.PositiveInfinity,20},30,10,true),"invalid bounds");
  Console.WriteLine("Selection range checks passed");
 }
}