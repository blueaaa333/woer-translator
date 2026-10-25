"""Map before applying native clipping; keep the clip in sync with actual size."""


def show_settings(app, window, radius=15):
    app.position_settings()
    window._rounded_size = None
    window._round_pending = False

    def refresh():
        window._round_pending = False
        if not window.winfo_exists() or not window.winfo_ismapped():
            return
        size = (window.winfo_width(), window.winfo_height())
        if size != window._rounded_size:
            window._rounded_size = size
            app.round_window(window, radius)

    def configured(event):
        if event.widget is window and not window._round_pending:
            window._round_pending = True
            window.after_idle(refresh)

    window.bind('<Configure>', configured, add='+')
    window.deiconify()
    window.update_idletasks()
    refresh()
    window.focus_set()
