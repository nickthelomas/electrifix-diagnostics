# AI Image Generation Prompt - Generic Scooter Diagram

## Prompt for Image Generator (MidJourney, DALL-E, Stable Diffusion, etc.)

```
Technical diagram of an electric scooter, side view, flat design, clean lines, white background.

Style: Technical schematic, workshop manual illustration, high contrast, clearly defined components.

Required components (all clearly labeled and distinct):
- Telescopic handlebar with throttle grip on right side
- Brake lever on left handlebar
- LCD dashboard display screen centered on handlebar
- Front headlight mounted on handlebar stem
- Front wheel with visible motor hub
- Rear wheel with visible motor hub
- Deck/footboard platform in center
- Battery pack compartment (visible outline under deck)
- Controller box near rear wheel
- Rear fender with brake light
- Folding mechanism at handlebar base
- Control buttons on left side of handlebar (3 mode buttons)

Art style: Minimal, technical, semi-transparent components showing internal parts, grayscale or simple color scheme with ability to overlay colored highlights.

Viewing angle: 90-degree side profile, left-facing, all components visible and accessible for overlay highlighting.

Technical requirements:
- High resolution (2048x2048 minimum)
- PNG with transparent background (or clean white background)
- Clear component separation for CSS/SVG overlays
- No human figures, no text labels needed
- Symmetric, centered composition
```

## Alternative Simpler Prompt:

```
Side view technical diagram of an electric scooter, workshop manual style, transparent background, all components visible and labeled: handlebars, throttle, brake lever, display screen, front wheel, rear wheel, battery pack, motor, controller box, headlight, brake light, deck. Clean lines, minimal style, high resolution PNG.
```

## Alternative Reference-Based Prompt:

```
Create a side-view technical illustration of a generic electric scooter similar to Xiaomi M365 or Ninebot style. Clean technical drawing style like a repair manual. Show: handlebar with controls, display, throttle grip, brake lever, front and rear wheels with hub motors, battery compartment under deck, controller box, headlight, brake light. White or transparent background, high contrast, suitable for digital overlay highlighting. Style: flat design, workshop technical diagram.
```

---

## Where to Save the Generated Image

### File Location:
```
/home/nick/electrifix-diagnostics/frontend/images/scooter-diagram.png
```

### Steps After Generation:

1. **Create the directory** (if it doesn't exist):
```bash
cd ~/electrifix-diagnostics
mkdir -p frontend/images
```

2. **Download your generated image** from the AI tool

3. **Rename it to**: `scooter-diagram.png`

4. **Copy to the project**:
```bash
cp ~/Downloads/your-generated-image.png ~/electrifix-diagnostics/frontend/images/scooter-diagram.png
```

5. **Verify it's there**:
```bash
ls -lh ~/electrifix-diagnostics/frontend/images/scooter-diagram.png
```

---

## Image Specifications

### Technical Requirements:
- **Format**: PNG (with transparency if possible)
- **Resolution**: Minimum 2048x2048px (or 2048 width for side view)
- **Aspect Ratio**: Roughly 2:1 or 3:1 (width:height) for side view
- **File Size**: Keep under 500KB for web performance
- **Color**: Grayscale or simple colors (will be highlighted with CSS)
- **Background**: Transparent or solid white

### Component Clarity:
Each component should be:
- **Visually distinct** from adjacent components
- **Large enough** to overlay highlights/animations
- **Positioned clearly** for identification

Key areas that need to be highlightable:
1. Throttle grip (right handlebar)
2. Brake lever (left handlebar)
3. Front wheel (for rotation animation)
4. Rear wheel (for rotation animation)
5. Headlight (for glow effect)
6. Brake light (for activation effect)
7. Display screen (for data pulse)
8. Battery area (for charge indication)
9. Mode buttons (for active state)
10. Controller box (for packet pulse)

---

## Example CSS Mapping Areas

After you have the image, you'll use CSS to create clickable/highlightable regions:

```css
/* Example positioning for highlights */
.scooter-diagram {
    position: relative;
    width: 100%;
    max-width: 800px;
}

.throttle-highlight {
    position: absolute;
    top: 15%;  /* Adjust based on actual image */
    right: 10%;
    width: 50px;
    height: 50px;
    border-radius: 50%;
    background: rgba(0, 255, 0, 0.3);
    pointer-events: none;
}

.wheel-front, .wheel-rear {
    position: absolute;
    width: 120px;
    height: 120px;
    /* Will contain rotating wheel overlay */
}
```

---

## If You Can't Generate an Image

### Option 1: Use a Simple SVG Placeholder
A basic SVG scooter shape can be created with code until you get a proper image.

### Option 2: Find a Stock Image
Search for:
- "electric scooter side view transparent background"
- "e-scooter technical diagram"
- "scooter illustration vector"

Ensure any stock image is licensed for commercial use.

### Option 3: Commission an Artist
Fiverr or similar platforms have technical illustrators who can create exactly what you need for $20-50.

---

## Testing the Image

Once placed, test in the browser:

1. Start the server
2. Open browser dev tools (F12)
3. Go to Network tab
4. Navigate to Component Test page
5. Check that `scooter-diagram.png` loads successfully
6. Verify it displays correctly in the layout

---

## Recommended AI Image Generators

**Free Options:**
- Bing Image Creator (DALL-E 3) - https://www.bing.com/images/create
- Leonardo.ai - Free tier available
- Adobe Firefly - Free tier

**Paid Options:**
- MidJourney - Best quality for technical diagrams
- DALL-E 3 (via ChatGPT Plus)
- Stable Diffusion (RunDiffusion, etc.)

**Tips for Best Results:**
- Try multiple generators and compare
- Generate 2-3 variations and pick the best
- Use "technical diagram" and "workshop manual" keywords
- Specify "side view" and "white background" clearly
- Request "high detail" and "clear components"
