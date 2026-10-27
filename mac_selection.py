"""Read accessibility selection state in an isolated, time-bounded helper."""
import base64,sys,math,threading,os

def verify(api,pid,x,y,expected=''):
    from lexicon import normalize_query,valid_query
    system=api.AXUIElementCreateSystemWide();api.AXUIElementSetMessagingTimeout(system,.15)
    error,focused=api.AXUIElementCopyAttributeValue(system,'AXFocusedApplication',None)
    if error:return False
    error,actual=api.AXUIElementGetPid(focused,None)
    if error or actual!=pid:return False
    app=api.AXUIElementCreateApplication(pid);api.AXUIElementSetMessagingTimeout(app,.15)
    def attribute(element,name):
        error,value=api.AXUIElementCopyAttributeValue(element,name,None)
        return value if error==0 else None
    if expected:element=attribute(app,'AXFocusedUIElement')
    else:
        error,element=api.AXUIElementCopyElementAtPosition(api.AXUIElementCreateSystemWide(),float(x),float(y),None)
        if error:return False
    for _ in range(6):
        if element is None:return False
        role=attribute(element,'AXRole')
        if role in ('AXSecureTextField','AXScrollBar','AXSlider','AXButton','AXImage','AXSplitter'):return False
        selected=attribute(element,'AXSelectedTextRange')
        if selected is not None:
            ok,span=api.AXValueGetValue(selected,api.kAXValueCFRangeType,None)
            if ok and 0<span[1]<=80:
                text=attribute(element,'AXSelectedText') or ''
                if not valid_query(normalize_query(text)):return False
                if expected:
                    if normalize_query(text).lower()==normalize_query(expected).lower():return True
                else:
                    error,bounds=api.AXUIElementCopyParameterizedAttributeValue(element,'AXBoundsForRange',selected,None)
                    if error==0:
                        ok,rect=api.AXValueGetValue(bounds,api.kAXValueCGRectType,None)
                        if ok:
                            (left,top),(width,height)=rect
                            if all(math.isfinite(v) for v in (left,top,width,height)) and width>0 and height>0 and left-12<=x<=left+width+12 and top-12<=y<=top+height+12:return True
        element=attribute(element,'AXParent')
    return False

def main():
    timer=threading.Timer(1.2,lambda:os._exit(4));timer.daemon=True;timer.start()
    try:
        import ApplicationServices as api
        args=sys.argv;index=args.index('--mac-verify-selection')
        pid,x,y=map(int,args[index+1:index+4]);line=sys.stdin.readline().strip();expected=base64.b64decode(line).decode() if line else ''
        print('SELECTED' if verify(api,pid,x,y,expected) else 'EMPTY',flush=True)
    except Exception:print('EMPTY',flush=True)
