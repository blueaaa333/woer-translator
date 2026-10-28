"""Only a newer outside mouse press dismisses a shown result window."""
def should_hide(detail,shown_at):
 if not detail or type(shown_at) not in (int,float):return False
 return detail.get('reason')=='pointer_down' and detail.get('at',0)>shown_at
