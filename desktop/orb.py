"""O orbe flutuante, desenhado com o Pillow numa janela própria do Windows.

Uma janela "em camadas" (UpdateLayeredWindow) recebe cada quadro com transparência por pixel: fora do
círculo ela é invisível e deixa o clique passar, e dentro dele recebe o clique normalmente. A janela
web do pywebview não consegue isso no Windows: fica um quadrado cinza ou para de receber cliques.
"""

import math
import threading
import time
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter


# Tamanho do orbe na tela, em pixels lógicos (é ajustado à escala do Windows).
SIZE = 150

# Distância do orbe até o canto inferior direito da área de trabalho.
MARGIN = 32

FRAME_MS = 33

BARS = 32

# Clique só conta se o mouse andou menos que isso entre apertar e soltar; senão, foi arrastar.
DRAG_PIXELS = 5

# O desenho é feito no dobro do tamanho e reduzido, para as bordas ficarem lisas.
SUPERSAMPLE = 2


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


@lru_cache(maxsize=4)
def base(size, accent):
    """O que não se move: o disco escuro, o brilho em volta e as marcas do aro."""

    color = rgb(accent)
    center = size / 2
    image = Image.new("RGBA", (size, size))

    glow = Image.new("RGBA", (size, size))
    ImageDraw.Draw(glow).ellipse([size * .2, size * .2, size * .8, size * .8], fill=(*color, 120))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size / 9)))

    disk = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(disk)
    radius = size * .44
    # Um disco escuro meio transparente: o orbe aparece sobre qualquer fundo e todo ele recebe o clique.
    draw.ellipse([center - radius, center - radius, center + radius, center + radius], fill=(7, 11, 18, 225), outline=(*color, 90), width=1)

    for tick in range(60):
        angle = math.radians(tick * 6)
        inner = radius - (5 if tick % 5 == 0 else 2.5)
        draw.line(
            [center + inner * math.cos(angle), center + inner * math.sin(angle),
             center + (radius - 1) * math.cos(angle), center + (radius - 1) * math.sin(angle)],
            fill=(*color, 110 if tick % 5 == 0 else 45), width=1
        )

    image.alpha_composite(disk)
    return image


@lru_cache(maxsize=4)
def core(size, accent):
    """O núcleo luminoso, branco no meio e da cor de destaque na borda."""

    color = rgb(accent)
    image = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(image)

    for step in range(size // 2, 0, -1):
        share = step / (size / 2)
        if share < .4:
            mix = share / .4
            fill = tuple(round(255 + (channel - 255) * mix) for channel in color)
        else:
            mix = (share - .4) / .6
            fill = tuple(round(channel + (dark - channel) * mix) for channel, dark in zip(color, (13, 21, 32)))
        draw.ellipse([size / 2 - step, size / 2 - step, size / 2 + step, size / 2 + step], fill=(*fill, 255))

    return image


def render(state, accent, seconds, size=SIZE):
    """Um quadro do orbe (RGBA) para o estado da voz: idle, listening, thinking ou speaking."""

    color = rgb(accent)
    image = base(size, accent).copy()
    big = size * SUPERSAMPLE
    center = big / 2
    layer = Image.new("RGBA", (big, big))
    draw = ImageDraw.Draw(layer)

    # O aro tracejado gira devagar; mais rápido ouvindo e bem rápido pensando.
    speed = {"listening": 120, "thinking": 420}.get(state, 18)
    radius = big * .3
    width = 2 * SUPERSAMPLE
    alpha = 230 if state in ("listening", "thinking") else 120

    for dash in range(16):
        start = dash * 22.5 + seconds * speed
        draw.arc([center - radius, center - radius, center + radius, center + radius], start, start + 12, fill=(*color, alpha), width=width)

    if state == "listening":
        # Ondas saindo do núcleo, como no protótipo.
        for wave in range(3):
            share = (seconds / 2.1 + wave / 3) % 1
            ring = big * (.16 + share * .26)
            draw.ellipse([center - ring, center - ring, center + ring, center + ring], outline=(*color, round(230 * (1 - share))), width=width)

    if state == "speaking":
        # Barras em volta do núcleo, como o equalizador do filme.
        for bar in range(BARS):
            angle = math.radians(bar * 360 / BARS)
            level = .3 + .7 * abs(math.sin(seconds * (5 + bar % 4) + bar * 1.7))
            inner = big * .33
            outer = inner + big * .09 * level
            draw.line(
                [center + inner * math.cos(angle), center + inner * math.sin(angle),
                 center + outer * math.cos(angle), center + outer * math.sin(angle)],
                fill=(*color, 240), width=width + 1
            )

    image.alpha_composite(layer.reduce(SUPERSAMPLE))

    # O núcleo "respira"; falando, respira mais rápido.
    period = .9 if state == "speaking" else 4
    scale = 1 + .07 * (math.sin(seconds * 2 * math.pi / period) + 1) / 2
    diameter = round(size * .36 * scale)
    nucleus = core(round(size * .36 * 1.07), accent).resize((diameter, diameter), Image.LANCZOS)
    image.alpha_composite(nucleus, ((size - diameter) // 2, (size - diameter) // 2))

    return image


class Orb:
    """A janela do orbe. Roda numa thread própria, com o laço de mensagens do Windows."""

    def __init__(self, accent):
        self.accent = accent
        self.state = "idle"
        self.hwnd = None

    def set_state(self, state):
        self.state = state

    def set_accent(self, color):
        self.accent = color

    def start(self, on_click, on_right_click, on_error):
        self.on_click = on_click
        self.on_right_click = on_right_click
        threading.Thread(target=self.run_safely, args=(on_error,), daemon=True).start()

    def destroy(self):
        if self.hwnd:
            win32().user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def run_safely(self, on_error):
        # Sem isso, um erro na thread do orbe some calado e o orbe só não aparece.
        try:
            self.run()

        except Exception as error:
            on_error(error)

    def run(self):
        api = win32()
        user32, gdi32 = api.user32, api.gdi32
        ctypes, w = api.ctypes, api.wintypes

        # O pywebview marca o processo como ciente da escala do Windows só depois de começar; esta
        # thread pode rodar antes. Fixando a escala aqui, tamanho e posição ficam sempre em pixels reais.
        user32.SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_SYSTEM_AWARE)

        self.proc = api.WNDPROC(self.handle)
        instance = api.kernel32.GetModuleHandleW(None)
        window_class = api.WNDCLASSEXW(
            cbSize=ctypes.sizeof(api.WNDCLASSEXW), lpfnWndProc=self.proc, hInstance=instance,
            hCursor=user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND)), lpszClassName="JarvisOrb"
        )
        if not user32.RegisterClassExW(ctypes.byref(window_class)) and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            raise ctypes.WinError(ctypes.get_last_error())

        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, "JarvisOrb", "JARVIS",
            WS_POPUP, 0, 0, 0, 0, None, None, instance, None
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        self.size = round(SIZE * user32.GetDpiForWindow(self.hwnd) / 96)
        area = w.RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
        margin = round(MARGIN * self.size / SIZE)
        user32.SetWindowPos(
            self.hwnd, None, area.right - self.size - margin, area.bottom - self.size - margin, self.size, self.size,
            SWP_NOZORDER | SWP_NOACTIVATE
        )

        self.screen = user32.GetDC(None)
        self.memory = gdi32.CreateCompatibleDC(self.screen)
        header = api.BITMAPINFOHEADER(
            biSize=ctypes.sizeof(api.BITMAPINFOHEADER), biWidth=self.size, biHeight=-self.size, biPlanes=1, biBitCount=32
        )
        self.bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(self.memory, ctypes.byref(header), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.memory, bitmap)

        self.started = time.monotonic()
        self.pressed = None
        self.draw()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetTimer(self.hwnd, 1, FRAME_MS, None)

        message = w.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def draw(self):
        api = win32()
        ctypes, w = api.ctypes, api.wintypes

        # O Windows quer os pixels em BGRA com o alfa já multiplicado.
        frame = render(self.state, self.accent, time.monotonic() - self.started, self.size)
        pixels = frame.convert("RGBa").tobytes("raw", "BGRa")
        ctypes.memmove(self.bits, pixels, len(pixels))

        blend = api.BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        if not api.user32.UpdateLayeredWindow(
            self.hwnd, self.screen, None, ctypes.byref(w.SIZE(self.size, self.size)), self.memory,
            ctypes.byref(w.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def handle(self, hwnd, message, wparam, lparam):
        api = win32()
        user32, ctypes, w = api.user32, api.ctypes, api.wintypes

        try:
            if message == WM_TIMER:
                self.draw()
                return 0

            if message == WM_LBUTTONDOWN:
                cursor, rect = w.POINT(), w.RECT()
                user32.GetCursorPos(ctypes.byref(cursor))
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                self.pressed = (cursor.x, cursor.y, rect.left, rect.top, False)
                user32.SetCapture(hwnd)
                return 0

            if message == WM_MOUSEMOVE and self.pressed:
                cursor = w.POINT()
                user32.GetCursorPos(ctypes.byref(cursor))
                x, y, left, top, dragging = self.pressed
                dx, dy = cursor.x - x, cursor.y - y

                if dragging or math.hypot(dx, dy) >= DRAG_PIXELS:
                    self.pressed = (x, y, left, top, True)
                    user32.SetWindowPos(hwnd, None, left + dx, top + dy, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                return 0

            if message == WM_LBUTTONUP and self.pressed:
                dragging = self.pressed[4]
                self.pressed = None
                user32.ReleaseCapture()

                if not dragging:
                    # Fora da thread da janela, para o orbe continuar animando.
                    threading.Thread(target=self.on_click, daemon=True).start()
                return 0

            if message == WM_RBUTTONUP:
                threading.Thread(target=self.on_right_click, daemon=True).start()
                return 0

            if message == WM_DESTROY:
                user32.KillTimer(hwnd, 1)
                user32.PostQuitMessage(0)
                return 0

        except Exception as error:
            print("ERRO NO ORBE:", repr(error))

        return user32.DefWindowProcW(hwnd, message, wparam, lparam)


DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
ERROR_CLASS_ALREADY_EXISTS = 1410
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x80000
WS_EX_TOPMOST = 0x8
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x1
SWP_NOZORDER = 0x4
SWP_NOACTIVATE = 0x10
SPI_GETWORKAREA = 0x30
IDC_HAND = 32649
ULW_ALPHA = 0x2
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
WM_DESTROY = 0x2
WM_CLOSE = 0x10
WM_TIMER = 0x113
WM_MOUSEMOVE = 0x200
WM_LBUTTONDOWN = 0x201
WM_LBUTTONUP = 0x202
WM_RBUTTONUP = 0x205


@lru_cache(maxsize=1)
def win32():
    """As funções do Windows usadas pelo orbe, com os tipos certos para Python de 64 bits."""

    import ctypes
    import types
    from ctypes import wintypes as w

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
            ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD), ("biBitCount", w.WORD),
            ("biCompression", w.DWORD), ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG),
            ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)
        ]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    # Cópias próprias das DLLs: os tipos definidos aqui não mexem nos de outras bibliotecas, e vice-versa.
    user32, gdi32, kernel32 = (ctypes.WinDLL(name, use_last_error=True) for name in ("user32", "gdi32", "kernel32"))
    # As funções do ctypes não servem de chave de dicionário, então a lista é de trios.
    signatures = [
        (user32.DefWindowProcW, [w.HWND, w.UINT, w.WPARAM, w.LPARAM], LRESULT),
        (user32.RegisterClassExW, [ctypes.POINTER(WNDCLASSEXW)], w.ATOM),
        (user32.CreateWindowExW, [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID], w.HWND),
        (user32.LoadCursorW, [w.HINSTANCE, ctypes.c_void_p], w.HANDLE),
        (user32.GetDpiForWindow, [w.HWND], w.UINT),
        (user32.SetThreadDpiAwarenessContext, [w.HANDLE], w.HANDLE),
        (user32.SystemParametersInfoW, [w.UINT, w.UINT, w.LPVOID, w.UINT], w.BOOL),
        (user32.SetWindowPos, [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT], w.BOOL),
        (user32.GetDC, [w.HWND], w.HDC),
        (user32.ShowWindow, [w.HWND, ctypes.c_int], w.BOOL),
        (user32.SetTimer, [w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID], ctypes.c_size_t),
        (user32.KillTimer, [w.HWND, ctypes.c_size_t], w.BOOL),
        (user32.GetMessageW, [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], w.BOOL),
        (user32.TranslateMessage, [ctypes.POINTER(w.MSG)], w.BOOL),
        (user32.DispatchMessageW, [ctypes.POINTER(w.MSG)], LRESULT),
        (user32.PostMessageW, [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
        (user32.UpdateLayeredWindow, [w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE), w.HDC,
                                      ctypes.POINTER(w.POINT), w.COLORREF, ctypes.POINTER(BLENDFUNCTION), w.DWORD], w.BOOL),
        (user32.GetCursorPos, [ctypes.POINTER(w.POINT)], w.BOOL),
        (user32.GetWindowRect, [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
        (user32.SetCapture, [w.HWND], w.HWND),
        (user32.ReleaseCapture, [], w.BOOL),
        (user32.PostQuitMessage, [ctypes.c_int], None),
        (gdi32.CreateCompatibleDC, [w.HDC], w.HDC),
        (gdi32.CreateDIBSection, [w.HDC, ctypes.POINTER(BITMAPINFOHEADER), w.UINT, ctypes.POINTER(ctypes.c_void_p),
                                  w.HANDLE, w.DWORD], w.HBITMAP),
        (gdi32.SelectObject, [w.HDC, w.HGDIOBJ], w.HGDIOBJ),
        (kernel32.GetModuleHandleW, [w.LPCWSTR], w.HMODULE)
    ]

    for function, arguments, result in signatures:
        function.argtypes = arguments
        function.restype = result

    return types.SimpleNamespace(
        ctypes=ctypes, wintypes=w, user32=user32, gdi32=gdi32, kernel32=kernel32,
        WNDPROC=WNDPROC, WNDCLASSEXW=WNDCLASSEXW, BITMAPINFOHEADER=BITMAPINFOHEADER, BLENDFUNCTION=BLENDFUNCTION
    )
