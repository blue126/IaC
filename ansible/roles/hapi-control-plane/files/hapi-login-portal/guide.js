const $ = id => document.getElementById(id);
const expectedWorkspace = JSON.parse(document.querySelector('meta[name="workspace-identity"]').content);
const prefix = '/_workspace/login';
const messages = {
    idle: ['尚未登录 Claude', '点击下方按钮，在本页完成 Claude 官方授权。'],
    running: ['正在进行 Claude 授权', '请在远程画面中完成登录和验证；完成后会自动检查结果。'],
    success: ['Claude 已登录', '可以返回 HAPI 创建或继续会话。'],
    failed: ['本次授权未完成', '可以重新开始授权。你的浏览器配置会继续保留。'],
    cancelled: ['已取消本次授权', '需要时可以重新开始；日常浏览器继续保留。'],
    expired: ['本次授权已超时', '请重新开始授权，并在 30 分钟内完成。'],
    unknown: ['暂时无法确认登录状态', '请稍后刷新；持续失败时联系管理员。'],
    blocked: ['需要检查当前认证配置', '当前使用其他认证来源，请联系管理员核对。']
};
let rfb = null;
let busy = false;
let polling = false;
let viewerWanted = false;
let connecting = false;
let revision = 0;
let actionError = false;
let viewTrusted = false;
let foreground = !document.hidden;
function dropViewer() {
    viewTrusted = false;
    viewerWanted = false;
    rfb?.disconnect();
    rfb = null;
    $('screen').replaceChildren();
    $('viewer-section').hidden = true;
    $('code-section').hidden = true;
}

function guardViewerInput(client, screen) {
    const modifiers = [
        ['shiftKey', 0xffe1, 'ShiftLeft'], ['shiftKey', 0xffe2, 'ShiftRight'],
        ['ctrlKey', 0xffe3, 'ControlLeft'], ['ctrlKey', 0xffe4, 'ControlRight'],
        ['altKey', 0xffe9, 'AltLeft'], ['altKey', 0xffea, 'AltRight'],
        ['metaKey', 0xffeb, 'MetaLeft'], ['metaKey', 0xffec, 'MetaRight']
    ];
    let connected = false;
    const release = event => {
        if (!connected) return;
        const altGraph = event?.getModifierState?.('AltGraph');
        for (const [flag, keysym, code] of modifiers) {
            // A lost key-up must not turn scrolling into history navigation,
            // zoom, or a WM shortcut. Preserve explicitly held shortcuts/AltGr.
            if (event?.[flag] || (altGraph && ['altKey', 'ctrlKey'].includes(flag))) continue;
            client.sendKey(keysym, code, false);
        }
    };
    const reset = () => release();
    const visibility = () => { if (document.hidden) reset(); };
    const connect = () => { connected = true; reset(); };
    const cleanup = () => {
        connected = false;
        screen.removeEventListener('wheel', release, true);
        screen.removeEventListener('mousedown', release, true);
        window.removeEventListener('blur', reset);
        document.removeEventListener('visibilitychange', visibility);
        client.removeEventListener('connect', connect);
        client.removeEventListener('disconnect', cleanup);
    };
    // Capture before noVNC emits the corresponding pointer/wheel packet.
    screen.addEventListener('wheel', release, {capture: true, passive: true});
    screen.addEventListener('mousedown', release, true);
    window.addEventListener('blur', reset);
    document.addEventListener('visibilitychange', visibility);
    client.addEventListener('connect', connect);
    client.addEventListener('disconnect', cleanup);
}

async function api(action, data) {
    const options = {headers: {}, cache: 'no-store', credentials: 'same-origin', redirect: 'error'};
    const identityResponse = await fetch('/_workspace/identity', {cache: 'no-store', credentials: 'same-origin', redirect: 'error'});
    if (!identityResponse.ok) { dropViewer(); throw new Error('入口身份已失效，请刷新页面。'); }
    const current = await identityResponse.json();
    if (['workspace_id', 'identity', 'generation'].some(key => current[key] !== expectedWorkspace[key])) {
        dropViewer();
        $('code').value = ''; $('clipboard').value = '';
        throw new Error('工作区身份已变化，请刷新页面。');
    }
    viewTrusted = foreground && !document.hidden;
    if (data !== undefined) {
        options.headers['X-Hapi-CSRF'] = current.csrf;
        options.method = 'POST';
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(data);
    }
    const response = await fetch(`${prefix}/api/login/${action}`, options);
    const result = await response.json();
    if (!response.ok) { if (response.status === 403) { viewerWanted = false; rfb?.disconnect(); } throw new Error(result.error || '操作未完成，请稍后重试。'); }
    return result;
}

async function connectViewer() {
    connecting = true;
    try {
        const {default: RFB} = await import(`${prefix}/core/rfb.js`);
        if (!viewerWanted || !viewTrusted) return;
        $('viewer-status').textContent = '正在连接远程浏览器…';
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const client = new RFB($('screen'), `${protocol}//${location.host}${prefix}/websockify`, {wsProtocols: ['binary']});
        rfb = client;
        client.scaleViewport = true;
        guardViewerInput(client, $('screen'));
        client.addEventListener('connect', () => {$('viewer-status').textContent = '已连接 VM 内的 Firefox，请在画面中操作。';});
        client.addEventListener('disconnect', () => {
            if (rfb === client) rfb = null;
            $('viewer-status').textContent = '画面连接已断开，正在等待重连；授权状态会继续检查。';
        });
    } catch {
        $('viewer-status').textContent = '远程画面暂时无法加载，请稍后刷新或取消本次授权。';
    } finally {connecting = false;}
}

function render(data) {
    const state = Object.hasOwn(messages, data.state) ? data.state : 'unknown';
    [$('status-title').textContent, $('status').textContent] = messages[state];
    $('start').hidden = !['idle', 'failed', 'cancelled', 'expired'].includes(state);
    $('start').textContent = state === 'idle' ? '开始 Claude 授权' : '重新开始授权';
    $('cancel').hidden = state !== 'running';
    $('return').hidden = state !== 'success';
    $('viewer-section').hidden = state !== 'running' || !data.viewer_ready;
    $('code-section').hidden = $('viewer-section').hidden;
    viewerWanted = state === 'running' && data.viewer_ready && viewTrusted;
    $('viewer-section').hidden = !viewerWanted;
    $('code-section').hidden = !viewerWanted;
    if (viewerWanted && !rfb && !connecting) connectViewer();
    else if (!viewerWanted && rfb) {
        rfb.disconnect();
        rfb = null;
    }
}

async function refresh() {
    if (polling || busy) return;
    polling = true;
    const version = revision;
    try {
        const data = await api('status');
        if (version === revision) {
            render(data);
            if (!actionError) $('error').hidden = true;
        }
    }
    catch (error) {dropViewer(); $('error').textContent = error.message; $('error').hidden = false;}
    finally {polling = false;}
}

async function act(action, data = {}) {
    if (busy) return;
    revision++;
    actionError = false;
    busy = true;
    document.querySelectorAll('button').forEach(button => {button.disabled = true;});
    try {
        render(await api(action, data));
        $('error').hidden = true;
        if (action === 'code') $('code-result').textContent = '已提交，请等待 Claude 验证结果。';
    } catch (error) {
        actionError = true;
        $('error').textContent = error.message;
        $('error').hidden = false;
    }
    finally {
        busy = false;
        document.querySelectorAll('button').forEach(button => {button.disabled = false;});
    }
}

$('start').addEventListener('click', () => act('start'));
$('cancel').addEventListener('click', () => act('cancel'));
$('code-form').addEventListener('submit', event => {
    event.preventDefault();
    const code = $('code').value.trim();
    $('code').value = '';
    act('code', {code});
});
$('fullscreen').addEventListener('click', () => {$('screen').requestFullscreen().catch(() => {});});
$('paste').addEventListener('click', () => {
    const text = $('clipboard').value;
    $('clipboard').value = '';
    if (!rfb || !text) return;
    rfb.clipboardPasteFrom(text);
    rfb.sendKey(0xffe3, 'ControlLeft', true);
    rfb.sendKey(0x0076, 'KeyV', true);
    rfb.sendKey(0x0076, 'KeyV', false);
    rfb.sendKey(0xffe3, 'ControlLeft', false);
    rfb.focus();
});
window.addEventListener('blur', () => { foreground = false; dropViewer(); });
window.addEventListener('focus', () => { foreground = true; refresh(); });
document.addEventListener('visibilitychange', () => {
    foreground = !document.hidden;
    if (!foreground) dropViewer(); else refresh();
});
refresh();
setInterval(refresh, 3000);
