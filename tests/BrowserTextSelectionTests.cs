using System;
class BrowserTextSelectionTests {
 class Reader:ISelectedTextReader {
  public int Start=0,End=5,Calls=0;public string Value="water";
  public int Count(){return 1;}
  public bool Range(int i,out int start,out int end){start=Start;end=End;return true;}
  public string Text(int start,int end){Calls++;return Value;}
  public double[] Bounds(int offset){return new double[]{100+offset*12,100,12,20};}
 }
 static void Check(bool pass,string name){if(!pass)throw new Exception(name);}
 static bool Probe(Reader reader,int x,string expected){return BrowserTextSelection.Check(reader,x,110,expected,s=>s.Trim(),s=>s=="water");}
 static void Main(){
  var r=new Reader();Check(Probe(r,130,null),"middle of word");Check(Probe(r,160,null),"word end");Check(!Probe(r,400,null),"far residual selection");
  Check(Probe(r,400,"water"),"explicit copy match");Check(!Probe(r,130,"table"),"stale clipboard mismatch");r.End=0;r.Calls=0;Check(!Probe(r,130,null)&&r.Calls==0,"collapsed range not read");r.End=90;Check(!Probe(r,130,null)&&r.Calls==0,"large range not read");
  Console.WriteLine("PASS IA2 selected text range checks");
 }
}
