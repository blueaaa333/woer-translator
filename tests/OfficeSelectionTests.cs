using System;
class OfficeSelectionTests {
 static void Check(bool pass,string label){if(!pass)throw new Exception(label);}
 static void Main(){
  Func<string,string> norm=s=>s.Trim();Func<string,bool> valid=s=>s=="water";
  Func<string> noRead=()=>{throw new Exception("must not read unsupported selection");};
  Check(OfficeSelection.Check(3,5,"lesson.pptx","lesson.pptx - WPS",()=>"water",norm,valid),"actual text selected");
  Check(!OfficeSelection.Check(2,5,"lesson.pptx","lesson.pptx - WPS",noRead,norm,valid),"shape selection");
  Check(!OfficeSelection.Check(3,0,"lesson.pptx","lesson.pptx - WPS",noRead,norm,valid),"collapsed caret");
  Check(!OfficeSelection.Check(3,81,"lesson.pptx","lesson.pptx - WPS",noRead,norm,valid),"bounded read");
  Check(!OfficeSelection.Check(3,5,"other.pptx","lesson.pptx - WPS",noRead,norm,valid),"stale background document");
  Console.WriteLine("PASS read-only Office selection checks");
 }
}
