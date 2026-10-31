/* Local editor assistance. This bridge never executes scripts or device actions. */
"use strict";
function startupFailure(message) {
    const element = document.getElementById("startup-error");
    if (element) { element.textContent = message; element.hidden = false; }
    console.error(message);
}
if (typeof QWebChannel !== "function" || typeof qt === "undefined" || !qt.webChannelTransport) {
    startupFailure("Local QWebChannel did not initialize. Open Help → Dependency health for supported repair guidance.");
} else new QWebChannel(qt.webChannelTransport, function (channel) {
    const bridge = channel.objects.editorBridge;
    function fail(message) {
        const detail = "Monaco initialization failed: " + String(message) + ". Open Help → Dependency health for supported repair guidance.";
        startupFailure(detail);
        bridge.reportError(detail);
    }
    if (typeof window.require !== "function" || typeof window.require.config !== "function") {
        fail("local AMD loader is missing, invalid or blocked");
        return;
    }
    window.addEventListener("unhandledrejection", event => fail(event.reason));
    window.addEventListener("error", event => bridge.reportError(String(event.message)));
    window.MonacoEnvironment = { getWorkerUrl: function () {
        const base = new URL("vendor/vs/", window.location.href).href;
        const code = "self.MonacoEnvironment={baseUrl:" + JSON.stringify(base) + "};importScripts(" +
            JSON.stringify(base + "base/worker/workerMain.js") + ");";
        return URL.createObjectURL(new Blob([code], {type: "text/javascript"}));
    }};
    require.config({ paths: { vs: "vendor/vs" } });
    require(["vs/editor/editor.main"], function () {
        bridge.apiCatalog(function (rawCatalog) {
            const catalog = JSON.parse(rawCatalog);
            const editor = monaco.editor.create(document.getElementById("editor"), {
                value: "", language: "python", theme: "vs-dark", automaticLayout: true,
                minimap: {enabled: false}, fontSize: 14, tabSize: 4, glyphMargin: true,
                scrollBeyondLastLine: false, accessibilitySupport: "auto"
            });
            let references = [];
            let imageDecorations = [];
            let executionDecorations = [];
            let breakpointDecorations = [];
            let changingDocument = false;
            function breakpointLines() {
                return [...new Set(breakpointDecorations.map(id => editor.getModel().getDecorationRange(id))
                    .filter(Boolean).map(range => range.startLineNumber))].sort((a,b) => a-b);
            }
            function reportBreakpoints() {
                window.studio.breakpoints = breakpointLines();
                bridge.breakpointsChanged(JSON.stringify({key: window.studio.documentKey,
                    revision: window.studio.documentRevision, lines: window.studio.breakpoints}));
            }
            function setBreakpoints(lines, key) {
                if (key !== undefined && key !== window.studio.documentKey) return;
                const valid = [...new Set(lines)].filter(line => Number.isInteger(line) && line > 0 && line <= editor.getModel().getLineCount()).slice(0, 1000);
                breakpointDecorations = editor.deltaDecorations(breakpointDecorations, valid.map(line => ({
                    range: new monaco.Range(line, 1, line, 1),
                    options: {glyphMarginClassName:"studio-breakpoint", glyphMarginHoverMessage: {value:"Click to remove breakpoint"},
                        stickiness:monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges}
                })));
                reportBreakpoints();
            }
            editor.onMouseDown(event => {
                if (event.target.type !== monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN || !event.target.position) return;
                const line = event.target.position.lineNumber;
                const lines = breakpointLines();
                setBreakpoints(lines.includes(line) ? lines.filter(value => value !== line) : [...lines, line]);
            });
            let imageRequest = 0;
            let debounce;
            const markdown = text => ({value: text, supportHtml: false, isTrusted: false});
            const quoteMarkdown = text => text.replace(/[\\`*_{}\[\]<>!]/g, "\\$&");

            function specFor(name, member) {
                return catalog.find(item => item.name === name && (!member || item.member_of === member));
            }

            function completionItems(model, position) {
                const word = model.getWordUntilPosition(position);
                const prefix = model.getLineContent(position.lineNumber).slice(0, position.column - 1);
                const member = /\bdevice\.[A-Za-z_]*$/.test(prefix) ? "device" :
                    /\.[A-Za-z_]*$/.test(prefix) ? "Pattern" : null;
                const range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn);
                const suggestions = catalog.filter(item => member ? item.member_of === member : item.kind !== "method")
                    .map(item => ({label: item.name,
                        kind: item.kind === "type" ? monaco.languages.CompletionItemKind.Class : monaco.languages.CompletionItemKind.Function,
                        insertText: item.name, detail: item.signature, documentation: item.documentation, range}));
                if (!member) suggestions.push({label: "device", kind: monaco.languages.CompletionItemKind.Variable,
                    insertText: "device", detail: "Device bound to this run's assigned phone", range});
                return {suggestions};
            }

            // API signature assistance; no source evaluation or project type inference.
            function signatureAt(model, position) {
                const from = Math.max(1, position.lineNumber - 30);
                const text = model.getValueInRange(new monaco.Range(from, 1, position.lineNumber, position.column));
                const stack = [];
                let quote = null, escaped = false, comment = false;
                for (let index = 0; index < text.length; index++) {
                    const char = text[index];
                    if (comment) { if (char === "\n") comment = false; continue; }
                    if (quote) {
                        if (escaped) escaped = false;
                        else if (char === "\\") escaped = true;
                        else if (char === quote) quote = null;
                        continue;
                    }
                    if (char === "#") { comment = true; continue; }
                    if (char === "'" || char === '"') { quote = char; continue; }
                    if ("([{".includes(char)) {
                        const match = char === "(" && text.slice(0, index).match(/((?:device\.)?[A-Za-z_]\w*)\s*$/);
                        stack.push({kind: char, name: match ? match[1] : null, commas: 0});
                    } else if (")]}".includes(char)) {
                        if (stack.length) stack.pop();
                    } else if (char === "," && stack.length) {
                        const frame = stack[stack.length - 1];
                        if (frame.kind === "(" && frame.name) frame.commas++;
                    }
                }
                const frame = stack.slice().reverse().find(item => item.name);
                if (!frame) return null;
                const pieces = frame.name.split(".");
                const item = specFor(pieces[pieces.length - 1], pieces.length > 1 ? "device" : null);
                if (!item) return null;
                return {signatures: [{label: (pieces.length > 1 ? "device." : "") + item.signature,
                    documentation: item.documentation,
                    parameters: item.parameters.map(p => ({label: p.label, documentation: p.name}))}],
                    activeSignature: 0, activeParameter: Math.min(frame.commas, Math.max(0, item.parameters.length - 1))};
            }

            function referenceAt(position) {
                return references.find(item => (position.lineNumber > item.start_line ||
                    position.lineNumber === item.start_line && position.column >= item.start_column) &&
                    (position.lineNumber < item.end_line || position.lineNumber === item.end_line && position.column <= item.end_column));
            }

            function hoverAt(model, position) {
                const image = referenceAt(position);
                if (image) return new Promise(resolve => bridge.imagePreview(image.reference, function (raw) {
                    const preview = JSON.parse(raw);
                    const contents = [markdown(quoteMarkdown(image.reference))];
                    if (preview.available) {
                        contents.push(markdown("![Captured image](" + preview.data_url + ")"));
                        contents.push(markdown(preview.width + " × " + preview.height + " pixels · current project image"));
                    } else contents.push(markdown(preview.error));
                    resolve({range: new monaco.Range(image.start_line, image.start_column, image.end_line, image.end_column), contents});
                }));
                const word = model.getWordAtPosition(position);
                const item = word && specFor(word.word);
                return item ? {contents: [markdown("```python\n" + item.signature + "\n```"), markdown(item.documentation)]} : null;
            }

            monaco.languages.registerCompletionItemProvider("python", {triggerCharacters: ["."], provideCompletionItems: completionItems});
            monaco.languages.registerSignatureHelpProvider("python", {
                signatureHelpTriggerCharacters: ["(", ","],
                provideSignatureHelp: function(model, position) {
                    const value = signatureAt(model, position);
                    return value ? {value, dispose: function () {}} : null;
                }
            });
            monaco.languages.registerHoverProvider("python", {provideHover: hoverAt});

            function refreshImages() {
                const version = editor.getModel().getVersionId();
                const request = ++imageRequest;
                bridge.imageReferences(editor.getValue(), function(raw) {
                    if (version !== editor.getModel().getVersionId() || request !== imageRequest) return;
                    references = JSON.parse(raw);
                    window.studio.imageReferences = references;
                    imageDecorations = editor.deltaDecorations(imageDecorations, references.map(item => ({
                        range: new monaco.Range(item.start_line, item.start_column, item.end_line, item.end_column),
                        options: {inlineClassName: item.available ? "studio-image-reference" : "studio-image-missing",
                            after: {content: item.available ? "  ▧" : "  ⚠", inlineClassName: "studio-image-hint"},
                            hoverMessage: markdown(item.message)}
                    })));
                    monaco.editor.setModelMarkers(editor.getModel(), "image-assets", references.filter(item => !item.available).map(item => ({
                        startLineNumber: item.start_line, startColumn: item.start_column,
                        endLineNumber: item.end_line, endColumn: item.end_column,
                        message: item.message, severity: monaco.MarkerSeverity.Warning
                    })));
                });
            }

            function setExecutionLine(line) {
                const valid = Number.isInteger(line) && line > 0 && line <= editor.getModel().getLineCount();
                window.studio.executionLine = valid ? line : null;
                executionDecorations = editor.deltaDecorations(executionDecorations, valid ? [{
                    range: new monaco.Range(line, 1, line, 1), options: {isWholeLine: true,
                        className: "studio-execution-line", glyphMarginClassName: "studio-execution-glyph",
                        stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges}
                }] : []);
            }

            function changed() {
                setExecutionLine(null);
                if (!changingDocument) {
                    reportBreakpoints();
                    bridge.documentSnapshotChanged(window.studio.documentKey,
                        window.studio.documentRevision, editor.getValue());
                }
                clearTimeout(debounce);
                debounce = setTimeout(() => {
                    const version = editor.getModel().getVersionId();
                    bridge.diagnostics(editor.getValue(), function(raw) {
                        if (version !== editor.getModel().getVersionId()) return;
                        monaco.editor.setModelMarkers(editor.getModel(), "python-syntax", JSON.parse(raw).map(d => ({
                            startLineNumber: d.line, startColumn: d.column, endLineNumber: d.line,
                            endColumn: d.column + 1, message: d.message, severity: monaco.MarkerSeverity.Error
                        })));
                    });
                    refreshImages();
                }, 200);
            }
            editor.onDidChangeModelContent(changed);
            window.studio = {
                documentKey: "default", documentRevision: 0, breakpoints: [], setBreakpoints,
                editor, apiCatalog: catalog, imageReferences: references, executionLine: null, runStatus: "Idle",
                setText: (source, key, lines, revision) => {
                    if (revision !== undefined && revision < window.studio.documentRevision) return;
                    window.studio.documentKey = key === undefined ? window.studio.documentKey : key;
                    if (revision !== undefined) window.studio.documentRevision = revision;
                    changingDocument = true;
                    try { editor.setValue(source); } finally { changingDocument = false; }
                    setBreakpoints(lines || []);
                    changed();
                }, getText: () => editor.getValue(),
                insert: (source, key, revision) => {
                    if (key !== undefined && (key !== window.studio.documentKey || revision !== window.studio.documentRevision)) return;
                    editor.executeEdits("automation-tool", [{range: editor.getSelection(), text: source, forceMoveMarkers: true}]);
                },
                completionItems, signatureAt, hoverAt, refreshImages, setExecutionLine,
                setRunStatus: status => { window.studio.runStatus = status; },
                setAppearance: (theme, fontSize) => {
                    monaco.editor.setTheme(theme === "light" ? "vs" : "vs-dark");
                    editor.updateOptions({fontSize});
                    document.body.style.background = theme === "light" ? "#ffffff" : "#1e1e1e";
                }
            };
            setInterval(refreshImages, 3000);
            bridge.editorReady();
        });
    }, fail);
});
