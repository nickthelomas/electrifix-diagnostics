# Component Test Enhancements - Implementation Prompt

## Repository
https://github.com/nickthelomas/electrifix-diagnostics

## Context
The Component Test feature has been implemented with Learn Mode and Test Mode, but needs two enhancements:

1. **Simulation mode for overlay testing** - Test SVG overlay animations without real hardware
2. **Baseline-aware model selection** - Only show models with captured baselines

---

## Enhancement 1: Simulation Mode in Component Test

### Current State
Component Test requires real hardware (USB-TTL adapter) to see live data and test overlay positioning.

### Required Feature
Add a **"Simulation Mode"** checkbox in Component Test that generates fake component data to test:
- SVG overlay positioning on the scooter diagram
- Wheel rotation animations
- Component highlight positions
- Throttle bar animations
- Real-time data panel updates

### Implementation Details

#### Frontend (frontend/index.html)

Add simulation mode toggle in Component Test tab:

```html
<!-- Add this near the top of Component Test view, before the Connect button -->
<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4">
    <label class="flex items-center cursor-pointer">
        <input type="checkbox" id="ct-simulation-mode" class="mr-3 h-5 w-5" onchange="toggleComponentTestSimulation()">
        <span class="font-medium">Use Simulation (Test Overlays)</span>
    </label>
    <p class="text-sm text-yellow-700 mt-1">Test overlay positioning and animations without hardware</p>
</div>
```

#### JavaScript Logic

Add to the Component Test JavaScript section:

```javascript
let ctSimulationMode = false;
let ctSimulationInterval = null;

function toggleComponentTestSimulation() {
    ctSimulationMode = document.getElementById('ct-simulation-mode').checked;

    if (ctSimulationMode) {
        // Disable real connection controls
        document.getElementById('ct-port-select').disabled = true;
        document.getElementById('ct-baud-select').disabled = true;

        showToast('Simulation mode enabled - generating fake component data');
    } else {
        // Re-enable controls
        document.getElementById('ct-port-select').disabled = false;
        document.getElementById('ct-baud-select').disabled = false;

        if (ctSimulationInterval) {
            clearInterval(ctSimulationInterval);
            ctSimulationInterval = null;
        }

        showToast('Simulation mode disabled');
    }
}

function startComponentTestSimulation() {
    if (!ctSimulationMode) return;

    let time = 0;
    const baseThrottle = 0;
    const baseSpeed = 0;

    ctSimulationInterval = setInterval(() => {
        time += 0.1;

        // Generate simulated component data with realistic patterns
        const fakeData = {
            throttle_percent: Math.max(0, Math.min(100, 50 + Math.sin(time) * 40)),
            brake_engaged: Math.sin(time * 2) > 0.8,
            speed_kmh: Math.abs(Math.sin(time * 0.5)) * 35,
            voltage: 52.0 + Math.sin(time * 0.3) * 2,
            current: Math.abs(Math.sin(time)) * 12,
            temperature: 30 + Math.abs(Math.sin(time * 0.2)) * 10,
            mode: ['eco', 'sport', 'turbo'][Math.floor(time / 5) % 3],
            headlight: Math.sin(time * 0.5) > 0,
            cruise: false,
            rpm: Math.abs(Math.sin(time * 0.7)) * 400,
            error_code: 0
        };

        // Update the display with simulated data
        updateComponentTestDisplay(fakeData);

    }, 100); // Update every 100ms
}

function stopComponentTestSimulation() {
    if (ctSimulationInterval) {
        clearInterval(ctSimulationInterval);
        ctSimulationInterval = null;
    }
}

// Modify the existing startComponentTest() function
function startComponentTest() {
    if (ctSimulationMode) {
        // Start simulation instead of real connection
        startComponentTestSimulation();
        isComponentTesting = true;
        document.getElementById('ct-btn-start').classList.add('hidden');
        document.getElementById('ct-btn-stop').classList.remove('hidden');
        return;
    }

    // ... existing real hardware connection code ...
}

// Modify the existing stopComponentTest() function
function stopComponentTest() {
    if (ctSimulationMode) {
        stopComponentTestSimulation();
        isComponentTesting = false;
        document.getElementById('ct-btn-start').classList.remove('hidden');
        document.getElementById('ct-btn-stop').classList.add('hidden');
        return;
    }

    // ... existing real hardware disconnect code ...
}
```

#### Testing Workflow

With simulation mode:
1. User checks "Use Simulation" checkbox
2. Clicks "Start Test"
3. System generates realistic fake data:
   - Throttle sweeps 0-100%
   - Brake pulses on/off
   - Speed varies
   - RPM changes (wheels should rotate)
   - Voltage/current/temperature fluctuate
   - Mode cycles through Eco/Sport/Turbo
4. User can **see exactly where overlays appear** on their scooter image
5. User can adjust SVG overlay positions in code to match image
6. No hardware needed!

---

## Enhancement 2: Baseline-Aware Model Selection

### Current State
- Model dropdown shows all 8 pre-seeded models
- Can select any model even without a baseline
- Test Mode can't compare if no baseline exists
- Learn Mode doesn't ask which model is being learned

### Required Feature
- **Learn Mode**: Ask user to select/create model before learning
- **Test Mode**: Only show models that have captured baselines in dropdown
- **Model Management**: Show baseline status next to each model
- **Empty State**: If no baselines exist, show helpful message

### Implementation Details

#### Database Schema (Already Exists)
The `component_baselines` table already has `model_id` foreign key.
The `scooter_models` table tracks models.

#### Backend API Enhancement (backend/main.py)

Modify the `/api/models` endpoint to include baseline status:

```python
@app.get("/api/models")
async def list_models():
    """List all scooter models with baseline status."""
    models = get_all_models()

    # Add baseline status to each model
    for model in models:
        baseline = get_component_baseline(model['id'])
        model['has_component_baseline'] = baseline is not None
        if baseline:
            model['baseline_captured_at'] = baseline.get('captured_at')

    return {"models": models}
```

Add endpoint to get models with baselines only:

```python
@app.get("/api/models/with-baselines")
async def list_models_with_baselines():
    """List only models that have component baselines."""
    all_models = get_all_models()
    models_with_baselines = []

    for model in all_models:
        baseline = get_component_baseline(model['id'])
        if baseline:
            model['baseline_captured_at'] = baseline.get('captured_at')
            models_with_baselines.append(model)

    return {"models": models_with_baselines}
```

#### Frontend: Learn Mode Flow

**Step 1: Model Selection Before Learning**

```html
<!-- Learn Mode - Step 1: Select/Create Model -->
<div id="learn-step-1" class="space-y-4">
    <h3 class="text-lg font-bold">Learn Mode - Select Scooter Model</h3>

    <p class="text-gray-600">
        Which scooter model are you capturing a baseline from?
    </p>

    <div>
        <label class="block text-sm font-medium mb-2">Select Existing Model</label>
        <select id="learn-model-select" class="w-full p-3 border rounded-lg">
            <option value="">-- Select a model --</option>
            <!-- Populated with ALL models from database -->
        </select>
    </div>

    <div class="text-center my-3 text-gray-500">- OR -</div>

    <div>
        <label class="block text-sm font-medium mb-2">Create New Model</label>
        <input type="text"
               id="learn-new-model-name"
               placeholder="e.g., Dragon GTR V3, Custom Build"
               class="w-full p-3 border rounded-lg mb-2">

        <div class="grid grid-cols-2 gap-2">
            <div>
                <label class="block text-xs text-gray-600 mb-1">Protocol</label>
                <select id="learn-new-protocol" class="w-full p-2 border rounded">
                    <option value="jp_qs_s4">JP/QS-S4 (1200)</option>
                    <option value="ninebot">Ninebot (115200)</option>
                </select>
            </div>
            <div>
                <label class="block text-xs text-gray-600 mb-1">Baud Rate</label>
                <input type="number"
                       id="learn-new-baud"
                       value="1200"
                       class="w-full p-2 border rounded">
            </div>
        </div>
    </div>

    <div class="flex gap-2">
        <button onclick="cancelLearnMode()"
                class="flex-1 py-3 bg-gray-300 rounded-lg">
            Cancel
        </button>
        <button onclick="startLearnWithModel()"
                class="flex-1 py-3 bg-blue-600 text-white rounded-lg font-bold">
            Start Learning
        </button>
    </div>
</div>
```

**JavaScript for Learn Mode:**

```javascript
async function startLearnMode() {
    // Show step 1: model selection
    document.getElementById('learn-step-1').classList.remove('hidden');

    // Load all models into dropdown
    const res = await fetch(API + '/api/models');
    const data = await res.json();
    const select = document.getElementById('learn-model-select');
    select.innerHTML = '<option value="">-- Select a model --</option>';

    data.models.forEach(model => {
        const hasBaseline = model.has_component_baseline ? ' ✓ (has baseline)' : '';
        const option = document.createElement('option');
        option.value = model.id;
        option.textContent = model.model_name + hasBaseline;
        select.appendChild(option);
    });
}

async function startLearnWithModel() {
    const selectedModelId = document.getElementById('learn-model-select').value;
    const newModelName = document.getElementById('learn-new-model-name').value.trim();

    let modelId = null;

    if (selectedModelId) {
        // Use existing model
        modelId = parseInt(selectedModelId);
    } else if (newModelName) {
        // Create new model first
        const protocol = document.getElementById('learn-new-protocol').value;
        const baudRate = parseInt(document.getElementById('learn-new-baud').value);

        const res = await fetch(API + '/api/models', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                model_name: newModelName,
                protocol: protocol,
                baud_rate: baudRate
            })
        });

        if (!res.ok) {
            showToast('Failed to create model', true);
            return;
        }

        const data = await res.json();
        modelId = data.id;
        showToast('Model created: ' + newModelName);
    } else {
        showToast('Please select or create a model', true);
        return;
    }

    // Store model ID for the learning session
    currentLearnModelId = modelId;

    // Hide step 1, proceed to guided sequence
    document.getElementById('learn-step-1').classList.add('hidden');

    // ... continue with existing learn mode steps ...
    proceedToLearnSequence(modelId);
}
```

#### Frontend: Test Mode - Models with Baselines Only

```javascript
async function loadTestModeModels() {
    const res = await fetch(API + '/api/models/with-baselines');
    const data = await res.json();

    const select = document.getElementById('test-model-select');

    if (data.models.length === 0) {
        // No baselines yet - show helpful message
        select.innerHTML = '<option value="">No baselines captured yet</option>';
        select.disabled = true;

        document.getElementById('test-empty-state').classList.remove('hidden');
        document.getElementById('test-empty-state').innerHTML = `
            <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-center">
                <p class="font-medium text-yellow-800 mb-2">No Baselines Available</p>
                <p class="text-sm text-yellow-700 mb-3">
                    You need to capture a baseline from a known-good scooter first.
                </p>
                <button onclick="switchToLearnMode()"
                        class="px-4 py-2 bg-blue-600 text-white rounded-lg">
                    Go to Learn Mode
                </button>
            </div>
        `;
        return;
    }

    // Populate dropdown with models that have baselines
    select.innerHTML = '<option value="">-- Select a model to test --</option>';
    select.disabled = false;

    data.models.forEach(model => {
        const option = document.createElement('option');
        option.value = model.id;
        const date = new Date(model.baseline_captured_at).toLocaleDateString();
        option.textContent = `${model.model_name} (baseline: ${date})`;
        select.appendChild(option);
    });
}
```

#### UI/UX Flow

**Learn Mode Flow:**
1. User clicks "Learn Mode"
2. System shows: "Which model are you learning?"
   - Dropdown with ALL existing models (shows which have baselines)
   - OR create new model fields
3. User selects/creates model
4. Click "Start Learning"
5. System proceeds to 8-step guided sequence
6. At end, saves baseline linked to that model
7. Model now appears in Test Mode dropdown

**Test Mode Flow:**
1. User clicks "Test Mode"
2. System loads models with baselines only
3. If no baselines: Show "Go to Learn Mode first" message
4. If baselines exist: Dropdown shows models with dates
5. User selects model → baseline loads
6. User connects scooter → real-time comparison begins

---

## Summary of Changes Required

### Backend (backend/main.py)
- [ ] Modify `/api/models` to include `has_component_baseline` field
- [ ] Add `/api/models/with-baselines` endpoint
- [ ] Ensure baseline creation links to correct model_id

### Frontend (frontend/index.html)
- [ ] Add simulation mode checkbox to Component Test
- [ ] Add simulation data generation function
- [ ] Modify Learn Mode to show model selection first
- [ ] Add "create new model" form in Learn Mode
- [ ] Modify Test Mode to load only models with baselines
- [ ] Add empty state message when no baselines exist
- [ ] Link model selection to learn/test workflows

### Expected User Experience

**Workshop Technician Flow:**
1. **First time:** No models have baselines
2. **Learn Mode:**
   - "Which scooter?" → Selects "Dragon GTR V2" or creates new
   - Follows guided test with known-good scooter
   - Baseline saved for Dragon GTR V2
3. **Test Mode:**
   - Dropdown now shows: "Dragon GTR V2 (baseline: Jan 16, 2026)"
   - Connects faulty Dragon GTR V2
   - System compares to baseline in real-time
   - Shows green/yellow/red indicators
4. **Over time:** Builds library of baselines for all scooter models in shop

**Overlay Testing Flow:**
1. Tech checks "Use Simulation"
2. Clicks "Start Test"
3. Sees throttle sweeping, wheels spinning, components highlighting
4. Adjusts SVG overlay positions in code to match image
5. Refreshes browser, tests again
6. Repeats until overlays perfectly align with scooter diagram
7. Unchecks simulation, ready for real testing

---

## Testing Checklist

After implementation, verify:

**Simulation Mode:**
- [ ] Checkbox enables/disables simulation
- [ ] Start button begins fake data generation
- [ ] Throttle bar animates smoothly
- [ ] Wheels rotate based on fake RPM
- [ ] Brake highlights pulse
- [ ] All data panels update
- [ ] Works without any hardware connected
- [ ] Can see overlay positioning clearly

**Learn Mode:**
- [ ] Shows model selection first
- [ ] Can select existing model
- [ ] Can create new model with protocol/baud
- [ ] Proceeds to 8-step sequence after selection
- [ ] Saves baseline linked to correct model_id
- [ ] Shows success message with model name

**Test Mode:**
- [ ] Only shows models with baselines
- [ ] Shows empty state if no baselines
- [ ] "Go to Learn Mode" button works
- [ ] Dropdown shows baseline capture dates
- [ ] Loads correct baseline when model selected
- [ ] Real-time comparison works

**Database:**
- [ ] component_baselines table links to correct model_id
- [ ] Can query models with/without baselines
- [ ] Multiple baselines per model handled correctly

---

## Implementation Priority

1. **Phase 1:** Model selection in Learn Mode (critical for baseline management)
2. **Phase 2:** Test Mode shows only models with baselines
3. **Phase 3:** Simulation mode for overlay testing

All three enhancements can be implemented independently.
