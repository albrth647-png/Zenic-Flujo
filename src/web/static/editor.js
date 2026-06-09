// Zenic-Flijo — Editor JS (Enhanced)

// ── Tool/Action mapping ────────────────────────────────────
const TOOL_ACTIONS = {
    crm: {
        label: 'CRM',
        actions: {
            create_lead: { label: 'Crear lead', params: ['name','email','phone','company','source','notes'] },
            update_lead: { label: 'Actualizar lead', params: ['lead_id','name','email','phone','stage'] },
            list_leads:  { label: 'Listar leads', params: ['stage'] },
            move_stage:  { label: 'Mover etapa', params: ['lead_id','stage'] },
        }
    },
    invoice: {
        label: 'Facturas',
        actions: {
            create_invoice: { label: 'Crear factura', params: ['client_name','client_email','items','tax_rate','discount','due_days','notes'] },
            list_invoices:  { label: 'Listar facturas', params: ['status'] },
            mark_paid:      { label: 'Marcar pagada', params: ['invoice_id'] },
        }
    },
    inventory: {
        label: 'Inventario',
        actions: {
            create_product:  { label: 'Crear producto', params: ['sku','name','description','category','stock','min_stock','price'] },
            update_stock:    { label: 'Actualizar stock', params: ['product_id','quantity','type','reason'] },
            list_products:   { label: 'Listar productos', params: [] },
            low_stock:       { label: 'Stock bajo', params: [] },
        }
    },
    notification: {
        label: 'Notificaciones',
        actions: {
            send_email:        { label: 'Enviar email', params: ['to','subject','body'] },
            send_notification:  { label: 'Enviar notificación', params: ['user_id','title','message'] },
        }
    },
    system: {
        label: 'Sistema',
        actions: {
            backup: { label: 'Backup', params: [] },
            log:    { label: 'Log', params: [] },
        }
    },
    subworkflow: {
        label: 'Sub-workflow',
        actions: {
            execute: { label: 'Ejecutar sub-workflow', params: ['workflow_id','input_mapping','output_mapping'] },
        }
    }
};

const PARAM_LABELS = {
    name:'Nombre', email:'Email', phone:'Teléfono', company:'Empresa', source:'Origen',
    notes:'Notas', lead_id:'ID Lead', stage:'Etapa', client_name:'Cliente', client_email:'Email cliente',
    items:'Items (JSON)', tax_rate:'Impuesto %', discount:'Descuento', due_days:'Días vencimiento',
    invoice_id:'ID Factura', status:'Estado', sku:'SKU', description:'Descripción', category:'Categoría',
    stock:'Stock', min_stock:'Stock mínimo', price:'Precio', product_id:'ID Producto', quantity:'Cantidad',
    type:'Tipo movimiento', reason:'Razón', to:'Para', subject:'Asunto', body:'Cuerpo',
    user_id:'ID Usuario', title:'Título', message:'Mensaje',
};

const EVENT_OPTIONS = [
    'crm.lead.created', 'crm.lead.updated', 'crm.lead.stage_changed',
    'invoice.created', 'invoice.paid', 'invoice.overdue',
    'inventory.stock_low', 'inventory.stock_updated', 'inventory.product_created',
];

let stepCounter = 0;
let currentWfId = null;
let workflowSaved = false;

// ── Trigger config UI ──────────────────────────────────────
function onTriggerTypeChange() {
    const type = document.getElementById('triggerType').value;
    const container = document.getElementById('triggerConfigContainer');

    switch (type) {
        case 'event':
            container.innerHTML = `
                <select id="triggerEvent">
                    ${EVENT_OPTIONS.map(e => `<option value="${e}">${e}</option>`).join('')}
                </select>`;
            break;
        case 'schedule':
            container.innerHTML = `
                <div class="schedule-config">
                    <select id="scheduleFreq" onchange="updateSchedulePreview()">
                        <option value="daily">Diario</option>
                        <option value="weekly">Semanal</option>
                        <option value="monthly">Mensual</option>
                    </select>
                    <input type="time" id="scheduleTime" value="23:00" onchange="updateSchedulePreview()">
                    <div id="schedulePreview" class="schedule-preview">Todos los días a las 11:00pm</div>
                </div>`;
            break;
        case 'webhook':
            container.innerHTML = `
                <div class="webhook-config">
                    <input type="text" id="webhookPath" placeholder="Path personalizado (opcional)" value="webhook">
                    <div class="webhook-preview">HTTP POST a <span id="webhookUrl">localhost:8081</span></div>
                </div>`;
            break;
        case 'manual':
            container.innerHTML = `<div class="manual-info">Ejecución manual — sin configuración adicional</div>`;
            break;
    }
}

function updateSchedulePreview() {
    const freq = document.getElementById('scheduleFreq').value;
    const time = document.getElementById('scheduleTime').value;
    const preview = document.getElementById('schedulePreview');
    if (!preview) return;
    const [h, m] = (time || '23:00').split(':');
    const hour12 = ((+h % 12) || 12);
    const ampm = +h >= 12 ? 'pm' : 'am';
    const timeStr = `${hour12}:${m}${ampm}`;
    const freqMap = { daily: 'Todos los días', weekly: 'Todas las semanas', monthly: 'Todos los meses' };
    preview.textContent = `${freqMap[freq]} a las ${timeStr}`;
}

function getTriggerConfig() {
    const type = document.getElementById('triggerType').value;
    switch (type) {
        case 'event':
            return { event: document.getElementById('triggerEvent')?.value || EVENT_OPTIONS[0] };
        case 'schedule': {
            const freq = document.getElementById('scheduleFreq')?.value || 'daily';
            const time = document.getElementById('scheduleTime')?.value || '23:00';
            return { frequency: freq, time: time };
        }
        case 'webhook':
            return { path: document.getElementById('webhookPath')?.value || 'webhook' };
        case 'manual':
            return {};
    }
    return {};
}

function setTriggerConfig(type, config) {
    document.getElementById('triggerType').value = type;
    onTriggerTypeChange();
    if (!config) return;
    setTimeout(() => {
        switch (type) {
            case 'event':
                if (config.event) {
                    const sel = document.getElementById('triggerEvent');
                    if (sel) sel.value = config.event;
                }
                break;
            case 'schedule':
                if (config.frequency) { const el = document.getElementById('scheduleFreq'); if (el) el.value = config.frequency; }
                if (config.time) { const el = document.getElementById('scheduleTime'); if (el) el.value = config.time; }
                updateSchedulePreview();
                break;
            case 'webhook':
                if (config.path) { const el = document.getElementById('webhookPath'); if (el) el.value = config.path; }
                break;
        }
    }, 50);
}

// ── Step management ─────────────────────────────────────────
function addStep(stepData) {
    stepCounter++;
    const num = stepCounter;
    const container = document.getElementById('stepsContainer');

    const card = document.createElement('div');
    card.className = 'step-card';
    card.dataset.stepId = num;
    card.draggable = true;

    card.innerHTML = `
        <div class="step-header">
            <div class="drag-handle" title="Arrastrar para reordenar">⠿</div>
            <div class="step-number">${num}</div>
            <span class="step-title">Paso ${num}</span>
            <div class="step-controls">
                <button class="btn btn-sm btn-danger btn-icon" onclick="removeStep(this)" title="Eliminar">✕</button>
            </div>
        </div>
        <div class="step-body">
            <div class="step-row">
                <div class="form-group" style="flex:1">
                    <label>Herramienta</label>
                    <select class="step-tool" onchange="onToolChange(this)">
                        ${Object.entries(TOOL_ACTIONS).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group" style="flex:1">
                    <label>Acción</label>
                    <select class="step-action" onchange="onActionChange(this)"></select>
                </div>
            </div>
            <div class="step-params-container"></div>
            <div class="form-group" style="margin-top:8px">
                <label>Condición (opcional)</label>
                <input type="text" class="step-condition" placeholder="Ej: stock < 10">
            </div>
        </div>
    `;

    container.appendChild(card);

    // Set tool and action
    const toolSel = card.querySelector('.step-tool');
    const actionSel = card.querySelector('.step-action');

    if (stepData) {
        if (stepData.tool) toolSel.value = stepData.tool;
        populateActions(toolSel, actionSel);
        if (stepData.action) actionSel.value = stepData.action;
        onActionChange(actionSel);
        if (stepData.params && typeof stepData.params === 'object') {
            setTimeout(() => {
                Object.entries(stepData.params).forEach(([k, v]) => {
                    const inp = card.querySelector(`.step-param-${k}`);
                    if (inp) inp.value = v;
                });
            }, 20);
        }
        if (stepData.condition) {
            card.querySelector('.step-condition').value = stepData.condition;
        }
    } else {
        populateActions(toolSel, actionSel);
        onActionChange(actionSel);
    }

    // Drag and drop events
    card.addEventListener('dragstart', onDragStart);
    card.addEventListener('dragend', onDragEnd);
    card.addEventListener('dragover', onDragOver);
    card.addEventListener('drop', onDrop);

    renumberSteps();
    updateConnectors();
}

// ── Drag & Drop ──────────────────────────────────────────────
let dragSrcElement = null;

function onDragStart(e) {
    dragSrcElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.stepId);
}

function onDragEnd() {
    this.classList.remove('dragging');
    document.querySelectorAll('.step-card.drag-over').forEach(el => el.classList.remove('drag-over'));
    dragSrcElement = null;
}

function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    document.querySelectorAll('.step-card.drag-over').forEach(el => el.classList.remove('drag-over'));
    this.classList.add('drag-over');
}

function onDrop(e) {
    e.preventDefault();
    this.classList.remove('drag-over');
    if (dragSrcElement === this) return;

    const container = document.getElementById('stepsContainer');
    const allCards = Array.from(container.querySelectorAll('.step-card'));
    const fromIndex = allCards.indexOf(dragSrcElement);
    const toIndex = allCards.indexOf(this);

    if (fromIndex === -1 || toIndex === -1) return;

    // Reorder by moving the dragged card before/after the target
    if (fromIndex < toIndex) {
        container.insertBefore(dragSrcElement, this.nextElementSibling);
    } else {
        container.insertBefore(dragSrcElement, this);
    }

    renumberSteps();
    updateConnectors();
}

// ── SVG Connectors ───────────────────────────────────────────
function updateConnectors() {
    const container = document.getElementById('stepsContainer');
    const cards = container.querySelectorAll('.step-card');

    // Remove all existing SVG connectors
    container.querySelectorAll('.step-svg-connector').forEach(el => el.remove());

    // Add connectors between cards
    cards.forEach((card, i) => {
        if (i === cards.length - 1) return;

        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'step-svg-connector');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '32');
        svg.setAttribute('viewBox', '0 0 100 32');
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.innerHTML = `<line x1="50" y1="0" x2="50" y2="24" stroke="#6366f1" stroke-width="2" opacity="0.4"/>
            <polygon points="44,24 50,32 56,24" fill="#6366f1" opacity="0.6"/>`;

        card.parentNode.insertBefore(svg, card.nextElementSibling);
    });
}

function populateActions(toolSel, actionSel) {
    const tool = toolSel.value;
    const actions = TOOL_ACTIONS[tool]?.actions || {};
    actionSel.innerHTML = Object.entries(actions).map(([k, v]) =>
        `<option value="${k}">${v.label}</option>`
    ).join('');
}

function onToolChange(toolSel) {
    const card = toolSel.closest('.step-card');
    const actionSel = card.querySelector('.step-action');
    populateActions(toolSel, actionSel);
    onActionChange(actionSel);
}

function onActionChange(actionSel) {
    const card = actionSel.closest('.step-card');
    const tool = card.querySelector('.step-tool').value;
    const action = actionSel.value;
    const paramsDef = TOOL_ACTIONS[tool]?.actions[action]?.params || [];
    const paramsContainer = card.querySelector('.step-params-container');

    if (paramsDef.length === 0) {
        paramsContainer.innerHTML = '<div class="no-params">Sin parámetros requeridos</div>';
        return;
    }

    paramsContainer.innerHTML = `<div class="params-grid">${
        paramsDef.map(p => `
            <div class="form-group param-field">
                <label>${PARAM_LABELS[p] || p}</label>
                <input type="text" class="step-param-${p}" placeholder="${PARAM_LABELS[p] || p}">
            </div>
        `).join('')
    }</div>`;
}

function removeStep(btn) {
    const card = btn.closest('.step-card');
    card.remove();
    renumberSteps();
    updateConnectors();
}

function renumberSteps() {
    const cards = document.querySelectorAll('#stepsContainer .step-card');
    cards.forEach((card, i) => {
        card.querySelector('.step-number').textContent = i + 1;
        card.querySelector('.step-title').textContent = `Paso ${i + 1}`;
        // Actualizar dataset para que coincida con el orden visual
        card.dataset.stepId = String(i + 1);
    });
}

// ── Collect data ────────────────────────────────────────────
function collectSteps() {
    const steps = [];
    document.querySelectorAll('#stepsContainer .step-card').forEach(card => {
        const tool = card.querySelector('.step-tool').value;
        const action = card.querySelector('.step-action').value;
        const paramsDef = TOOL_ACTIONS[tool]?.actions[action]?.params || [];
        const params = {};
        paramsDef.forEach(p => {
            const inp = card.querySelector(`.step-param-${p}`);
            if (inp && inp.value.trim()) params[p] = inp.value.trim();
        });
        const condition = card.querySelector('.step-condition').value.trim();
        steps.push({
            id: parseInt(card.dataset.stepId),
            tool, action, params,
            condition: condition || undefined,
        });
    });
    return steps;
}

function collectWorkflowData() {
    return {
        name: document.getElementById('wfNameInput').value.trim() || 'Workflow sin nombre',
        trigger_type: document.getElementById('triggerType').value,
        trigger_config: getTriggerConfig(),
        steps: collectSteps(),
    };
}

// ── Save workflow ───────────────────────────────────────────
async function saveWorkflow() {
    const data = collectWorkflowData();
    try {
        if (currentWfId) {
            await api(`/api/workflows/${currentWfId}`, { method: 'PUT', body: JSON.stringify(data) });
            showToast('Workflow actualizado ✅');
        } else {
            const result = await api('/api/workflows', { method: 'POST', body: JSON.stringify(data) });
            if (result?.id) {
                currentWfId = result.id;
                window.history.replaceState({}, '', `/editor?wf=${result.id}`);
                document.getElementById('editorTitle').textContent = `✏️ Editando: ${data.name}`;
                document.getElementById('btnActivate').disabled = false;
                showToast('Workflow creado ✅');
            } else {
                showToast('Error: ' + (result?.error || 'desconocido'), true);
                return null;
            }
        }
        workflowSaved = true;
        return currentWfId;
    } catch (e) {
        showToast('Error al guardar: ' + e.message, true);
        return null;
    }
}

// ── Test workflow ───────────────────────────────────────────
async function testWorkflow() {
    const wfId = await saveWorkflow();
    if (!wfId) return;

    const resultDiv = document.getElementById('testResult');
    resultDiv.classList.remove('hidden');
    resultDiv.className = 'test-result test-loading';
    resultDiv.textContent = 'Ejecutando prueba...';

    try {
        const result = await api(`/api/workflows/${wfId}/retry`, { method: 'POST' });
        resultDiv.className = 'test-result ' + (result?.status === 'completed' ? 'test-success' : result?.error ? 'test-error' : 'test-info');
        if (result?.status) {
            resultDiv.innerHTML = `<strong>Estado:</strong> ${result.status} ${result.status === 'completed' ? '✅' : '⚠️'}`;
            if (result.duration_ms) resultDiv.innerHTML += ` <strong>Duración:</strong> ${result.duration_ms}ms`;
        } else if (result?.error) {
            resultDiv.innerHTML = `<strong>Error:</strong> ${result.error}`;
        } else {
            resultDiv.textContent = JSON.stringify(result, null, 2);
        }
    } catch (e) {
        resultDiv.className = 'test-result test-error';
        resultDiv.textContent = 'Error: ' + e.message;
    }
}

// ── Activate workflow ───────────────────────────────────────
async function activateWorkflow() {
    const wfId = await saveWorkflow();
    if (!wfId) return;

    try {
        const result = await api(`/api/workflows/${wfId}/activate`, { method: 'POST' });
        if (result?.status === 'active') {
            showToast('Workflow activado ✅');
        } else {
            showToast('Error al activar: ' + (result?.error || 'estado inesperado'), true);
        }
    } catch (e) {
        showToast('Error al activar: ' + e.message, true);
    }
}

// ── Cancel ──────────────────────────────────────────────────
function cancelEdit() {
    if (confirm('¿Salir sin guardar? Los cambios se perderán.')) {
        window.location.href = '/workflows';
    }
}

// ── Toast notification ──────────────────────────────────────
function showToast(msg, isError = false) {
    let toast = document.getElementById('editorToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'editorToast';
        toast.className = 'editor-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = 'editor-toast' + (isError ? ' toast-error' : ' toast-success');
    toast.classList.add('toast-visible');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('toast-visible'), 3000);
}

// ── Load existing workflow ──────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    currentWfId = new URLSearchParams(window.location.search).get('wf');
    if (!currentWfId) {
        addStep();
        onTriggerTypeChange();
        return;
    }

    try {
        const wf = await api(`/api/workflows/${currentWfId}`);
        if (!wf) { addStep(); onTriggerTypeChange(); return; }

        document.getElementById('wfNameInput').value = wf.name || '';
        document.getElementById('editorTitle').textContent = `✏️ Editando: ${wf.name || 'Sin nombre'}`;
        document.getElementById('btnActivate').disabled = false;

        setTriggerConfig(wf.trigger_type || 'event', wf.trigger_config || {});

        (wf.steps || []).forEach(s => addStep(s));
        if (!wf.steps?.length) addStep();
    } catch (e) {
        addStep();
        onTriggerTypeChange();
    }
});
