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
let frame = null;
let busy = false;
let polling = false;
let viewerWanted = false;
let revision = 0;
let actionError = false;
let viewTrusted = false;
let foreground = !document.hidden;
// The remote Firefox needs precise clicks and a keyboard, which phones do not provide;
// a touch-only device is sent to a computer instead of starting an authorization it cannot finish.
const touchOnly = matchMedia('(pointer: coarse)').matches && !matchMedia('(any-pointer: fine)').matches;
function stopViewer() {
    frame?.remove();
    frame = null;
}

function dropViewer() {
    viewTrusted = false;
    viewerWanted = false;
    stopViewer();
    $('screen').replaceChildren();
    $('remote-text').value = '';
    $('remote-copy').hidden = true;
    $('viewer-section').hidden = true;
    $('code-section').hidden = true;
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
    if (!response.ok) { if (response.status === 403) { viewerWanted = false; stopViewer(); } throw new Error(result.error || '操作未完成，请稍后重试。'); }
    return result;
}

// The Kasm client speaks the server's own protocol. Embedded without show_control_bar it hides its
// control bar and clipboard, so the clipboard is enabled here; state comes back by postMessage.
function connectViewer() {
    const settings = new URLSearchParams({
        autoconnect: '1', path: `${prefix.slice(1)}/websockify`, resize: 'scale',
        clipboard_up: 'true', clipboard_down: 'true', clipboard_seamless: 'true'
    });
    $('viewer-status').textContent = '正在连接远程浏览器…';
    frame = document.createElement('iframe');
    frame.title = '本人 VM 远程 Firefox';
    frame.src = `${prefix}/kasm/index.html?${settings}`;
    // Focus inside the frame blurs only the frame's window once it leaves the browser.
    frame.addEventListener('load', event => event.target.contentWindow.addEventListener('blur', checkForeground));
    $('screen').replaceChildren(frame);
}

function kasmMessage(event) {
    if (!frame || event.source !== frame.contentWindow || event.origin !== location.origin) return;
    const {action, value} = event.data ?? {};
    if (action === 'connection_state' && value === 'connected') $('viewer-status').textContent = '已连接 VM 内的 Firefox，请在画面中操作。';
    // Only Chromium lets the client write the local clipboard itself; elsewhere the text ends here.
    if (action === 'clipboardrx' && typeof value === 'string') {
        $('remote-text').value = value;
        $('remote-copy').hidden = !value;
    }
    // On idle timeout the client leaves for disconnected.html without reporting a state change.
    if (action === 'idle_session_timeout' || (action === 'connection_state' && value === 'disconnected')) {
        stopViewer();
        $('viewer-status').textContent = '画面连接已断开，正在等待重连；授权状态会继续检查。';
    }
}

// Moving focus into the frame blurs this window too; only a page without focus has lost it.
function checkForeground() {
    setTimeout(() => {
        if (document.hasFocus()) return;
        foreground = false;
        dropViewer();
    });
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
    if (touchOnly && ['idle', 'running', 'failed', 'cancelled', 'expired'].includes(state)) {
        $('status-title').textContent = '请在电脑上完成 Claude 登录';
        $('status').textContent = 'Claude 授权需要在远程画面里点击和输入，手机上无法完成。请用电脑浏览器打开 HAPI，再点击“Claude 登录”。';
        $('start').hidden = true;
        viewerWanted = false;
        $('viewer-section').hidden = true;
        $('code-section').hidden = true;
    }
    if (viewerWanted && !frame) connectViewer();
    else if (!viewerWanted) stopViewer();
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
    if (!frame || !text) return;
    frame.contentWindow.postMessage({action: 'clipboardsnd', value: text}, location.origin);
    frame.focus();
    $('viewer-status').textContent = '文本已发送到远程剪贴板，请在远程输入框中按 Ctrl+V 粘贴。';
});
window.addEventListener('message', kasmMessage);
window.addEventListener('blur', checkForeground);
window.addEventListener('focus', () => { foreground = true; refresh(); });
document.addEventListener('visibilitychange', () => {
    foreground = !document.hidden;
    if (!foreground) dropViewer(); else refresh();
});
refresh();
setInterval(refresh, 3000);
