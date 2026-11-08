import sys, asyncio, pathlib
from playwright.async_api import async_playwright

# build.py <file.html> <outdir> <w> <h> [scale] [quality]
async def main():
    src = pathlib.Path(sys.argv[1]).resolve()
    outdir = pathlib.Path(sys.argv[2]); outdir.mkdir(parents=True, exist_ok=True)
    w, h = int(sys.argv[3]), int(sys.argv[4])
    scale = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
    q = int(sys.argv[6]) if len(sys.argv) > 6 else 92
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
        await pg.goto(src.as_uri())
        await pg.wait_for_load_state("networkidle")
        await pg.evaluate("document.fonts.ready")
        await pg.wait_for_timeout(800)
        slides = await pg.query_selector_all(".slide")
        for el in slides:
            name = await el.get_attribute("data-name")
            out = outdir / f"{name}.jpg"
            await el.screenshot(path=str(out), type="jpeg", quality=q)
            print(f"  ✓ {out.name}")
        await b.close()

asyncio.run(main())
