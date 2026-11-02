"""LTH Overlays paleidimas (šis failas atnaujinimų metu nekeičiamas - laikyk jį paprastą)."""
import sys

try:
    import lth_boot
    updated = lth_boot.apply_pending()
except Exception:  # noqa: BLE001 - paleidimas svarbiau už atnaujinimą
    lth_boot = None
    updated = None

try:
    from lth_overlays.app import main
except Exception:  # noqa: BLE001
    # nauja versija nepasileidžia - grąžinam ankstesnę
    if updated and lth_boot is not None and lth_boot.rollback():
        for m in [m for m in sys.modules if m.startswith(("lth_overlays", "lth_timing"))]:
            del sys.modules[m]
        from lth_overlays.app import main
    else:
        raise

if __name__ == "__main__":
    sys.exit(main())
