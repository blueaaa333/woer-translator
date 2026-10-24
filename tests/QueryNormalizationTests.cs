using System;
using System.Reflection;
class QueryNormalizationTests {
 static int Main(string[] args) {
  var type=Assembly.LoadFrom(args[0]).GetType("DesktopBridge");
  var normalize=type.GetMethod("NormalizeQuery",BindingFlags.Static|BindingFlags.NonPublic);
  var valid=type.GetMethod("ValidQuery",BindingFlags.Static|BindingFlags.NonPublic);
  foreach(string value in new[]{"well-researched","well\u2011researched","well\u2013researched","well-\nresearched","well researched"}) {
   string result=(string)normalize.Invoke(null,new object[]{value});
   if(!(bool)valid.Invoke(null,new object[]{result}))throw new Exception("Compound rejected");
  }
  if((bool)valid.Invoke(null,new object[]{new string('a',81)}))throw new Exception("Truncated selection accepted");
  if((bool)valid.Invoke(null,new object[]{"hello 123"}))throw new Exception("Nontext accepted");
  Console.WriteLine("PASS native UIA/speech normalization: 5 compound variants and 2 invalid selections");return 0;
 }
}
