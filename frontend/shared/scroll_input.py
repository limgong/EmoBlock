"""Translate Tk 9 touchpad deltas into smooth canvas movement."""


def bind_touchpad(root, handler):
    if root.tk.call('info', 'commands', 'tk::PreciseScrollDeltas'):
        root.bind_all('<TouchpadScroll>', handler, add='+')


def touchpad_deltas(event):
    return tuple(map(int, event.widget.tk.call('tk::PreciseScrollDeltas', event.delta)))


def scroll_canvas_pixels(canvas, axis, delta):
    if not delta:
        return
    region = canvas.tk.splitlist(canvas.cget('scrollregion'))
    if len(region) != 4:
        return
    start, end = (float(region[0]), float(region[2])) if axis == 'x' else (float(region[1]), float(region[3]))
    length = end - start
    if length <= 0:
        return
    view = canvas.xview if axis == 'x' else canvas.yview
    move = canvas.xview_moveto if axis == 'x' else canvas.yview_moveto
    move(view()[0] - delta / length)
