from desktop import orb


def test_outside_the_circle_is_fully_transparent():
    frame = orb.render("idle", "#3FD4F5", 0)

    assert frame.size == (orb.SIZE, orb.SIZE)
    for corner in [(0, 0), (orb.SIZE - 1, 0), (0, orb.SIZE - 1), (orb.SIZE - 1, orb.SIZE - 1)]:
        assert frame.getpixel(corner)[3] == 0


def test_the_whole_disk_is_opaque_enough_to_take_clicks():
    frame = orb.render("idle", "#3FD4F5", 0)
    center = orb.SIZE // 2

    for x in range(center - 60, center + 61, 10):
        assert frame.getpixel((x, center))[3] > 0


def test_each_voice_state_looks_different():
    frames = [orb.render(state, "#3FD4F5", 1.3).tobytes() for state in ["idle", "listening", "thinking", "speaking"]]

    assert len(set(frames)) == 4


def test_accent_color_and_scale_are_used():
    cyan = orb.render("idle", "#3FD4F5", 0, 300)
    gold = orb.render("idle", "#F5B83F", 0, 300)

    assert cyan.size == (300, 300)
    assert cyan.getpixel((150, 150 - 40))[:3] != gold.getpixel((150, 150 - 40))[:3]


def test_an_error_in_the_orb_thread_is_reported(monkeypatch):
    shown = orb.Orb("#3FD4F5")
    errors = []

    def fail():
        raise OSError("sem janela")

    monkeypatch.setattr(shown, "run", fail)
    shown.run_safely(errors.append)

    assert str(errors[0]) == "sem janela"


def test_the_disk_background_is_see_through():
    frame = orb.render("idle", "#3FD4F5", 0, 300)

    # Entre o aro tracejado e as marcas da borda só há o véu do disco.
    assert frame.getpixel((150 + 112, 150))[3] < 128
