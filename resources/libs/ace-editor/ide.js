const editor = ace.edit("editor2");
const savedLanguage = localStorage.getItem("language") || "c";
const savedTheme = localStorage.getItem("theme") || "textmate";
editor.setShowPrintMargin(false);

let languageCodeSamples = {
    "c": "#include <stdio.h>\nint main() {\n    printf(\"Hello, World!\\n\");\n    return 0;\n}",
    "cpp": "#include <iostream>\nusing namespace std;\nint main() {\n    cout << \"Hello, World!\" << endl;\n    return 0;\n}",
    "java": "public class Main {\n    public static void main(String[] args) {\n        System.out.println(\"Hello, World!\");\n    }\n}",
    "kotlin": "fun main() {\n    println(\"Hello, World!\")\n}",
    "pascal": "program HelloWorld;\nbegin\n    writeln('Hello, World!');\nend.",
    "pypy": "print('Hello, World!')",
    "python": "print('Hello, World!')",
    "scratch": "// Scratch is a visual programming language, no text code required"
};

let languageFileNames = {
    "c": "main.c",
    "cpp": "main.cpp",
    "java": "Main.java",
    "kotlin": "Main.kt",
    "pascal": "Main.pas",
    "pypy": "main.py",
    "python": "main.py",
    "scratch": "main.sb3"
};


document.getElementById("theme").addEventListener("change", function () {
    editor.setTheme("ace/theme/" + this.value);
    localStorage.setItem("theme", this.value);
});

document.getElementById("language").addEventListener("change", function () {
    const selectedLang = this.value;

    if (selectedLang == 'c' || selectedLang == 'cpp') {
        editor.session.setMode("ace/mode/c_cpp");
    } else {
        editor.session.setMode("ace/mode/" + selectedLang);
    };

    editor.setValue(languageCodeSamples[selectedLang]);
    editor.clearSelection();
    const fileName = languageFileNames[selectedLang];
    document.querySelector(".ace_wrapper .file-name").value = fileName;
    localStorage.setItem("language", selectedLang);
});

document.getElementById("language").value = savedLanguage;
document.getElementById("theme").value = savedTheme;
document.querySelector(".ace_wrapper .file-name").value = languageFileNames[savedLanguage];
if (savedLanguage == 'c' || savedLanguage == 'cpp') {
    editor.session.setMode("ace/mode/c_cpp");
} else {
    editor.session.setMode("ace/mode/" + savedLanguage)
};
editor.setValue(languageCodeSamples[savedLanguage]);

editor.clearSelection();
if (this.value == 'c' || this.value == 'cpp') {
    editor.setTheme("ace/theme/c_cpp");
} else {
    editor.setTheme("ace/theme/" + savedTheme)
};


function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    const index = tabId === 'input-tab' ? 0 : 1;
    document.querySelectorAll('.tab-button')[index].classList.add('active');
}

let terminal = document.getElementById("terminal");
let input = document.getElementById("input");

function saveFile() {
    let code = editor.getValue();
    let filename = document.querySelector('.ace_wrapper .file-name').value || "main.c";
    if (!filename) return;

    let blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    let link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function showIde(){
    document.querySelector('.ace_wrapper').style.display = 'block';
    document.querySelector('.ide-btn').style.display = 'none';
    document.querySelector('#page-container').classList.add('ide-open');
    document.querySelector('main#content').classList.add('ide-content');
    const pdfContainer = document.querySelector('object#pdfContainer');

    if (pdfContainer) {
        const contentLeft = document.querySelector('#content-left.split-common-content');
        if (contentLeft) contentLeft.classList.add('ide-active');

        const commonContent = document.querySelector('#common-content');
        if (commonContent) commonContent.classList.add('ide-active');

        const contentRight = document.querySelector('#content-body #content-right');
        if (contentRight) contentRight.classList.add('ide-active');
    }
    const langMap = {
        'c': 'c',
        'c++': 'cpp',
        'cpp': 'cpp',
        'cpp20': 'cpp',
        'java': 'java',
        'kotlin': 'kotlin',
        'pascal': 'pascal',
        'pas': 'pascal',
        'pypy': 'pypy',
        'py3': 'python',
        'python': 'python',
        'output only': null
    };
    const langSelect = document.querySelector('#language');
    const toggledEl = document.querySelector('#allowed-langs .toggled');
    if (!toggledEl) {
        console.warn('[showIde] allowed-langs not found');
    } else {
        const allowedLangsRaw = Array.from(toggledEl.childNodes)
            .filter(node => node.nodeType === Node.TEXT_NODE || (node.tagName !== 'S'))
            .map(node => node.textContent.trim().toLowerCase())
            .flatMap(text => text.split(','))
            .map(lang => lang.trim())
            .filter(lang => lang);

        const allowedLangs = allowedLangsRaw
            .map(name => langMap[name])
            .filter(Boolean);

        let foundAny = false;
        Array.from(langSelect.options).forEach(option => {
            const isAllowed = allowedLangs.includes(option.value);
            option.style.display = isAllowed ? '' : 'none';
            if (isAllowed) foundAny = true;
        });

        if (!foundAny) {
            disableEditorAndLangs(langSelect);
            console.warn('[showIde] No valid languages allowed!');
        } else {
            const selected = langSelect.options[langSelect.selectedIndex];
            if (!selected || selected.style.display === 'none') {
                const firstVisible = Array.from(langSelect.options).find(o => o.style.display !== 'none');
                if (firstVisible) {
                    Array.from(langSelect.options).forEach(o => o.selected = false);
                    firstVisible.selected = true;
                    langSelect.selectedIndex = Array.from(langSelect.options).indexOf(firstVisible);
                }
            }
        }
    }
    let selectedLanguageEditor = document.getElementById("language").value;
    editor.setValue(languageCodeSamples[selectedLanguageEditor]);
    editor.clearSelection();
    if (selectedLanguageEditor == 'c' || selectedLanguageEditor == 'cpp') {
        editor.session.setMode("ace/mode/c_cpp");
    } else {
        editor.session.setMode("ace/mode/" + selectedLanguageEditor);
    };
}

function disableEditorAndLangs(langSelect) {
    editor.setValue('');
    editor.setReadOnly(true);
    editor.renderer.$cursorLayer.element.style.display = "none";
    if (langSelect) {
        langSelect.selectedIndex = -1;
        Array.from(langSelect.options).forEach(option => {
            option.style.display = 'none';
        });
    }
}
function hideIde(){
    document.querySelector('.ace_wrapper').style.display = 'none';
    document.querySelector('.ide-btn').style.display = 'block';
    document.querySelector('#page-container').classList.remove('ide-open');
    document.querySelector('main#content').classList.remove('ide-content');
    const pdfContainer = document.querySelector('object#pdfContainer');

    if (pdfContainer) {
        const contentLeft = document.querySelector('#content-left.split-common-content');
        if (contentLeft) contentLeft.classList.remove('ide-active');

        const commonContent = document.querySelector('#common-content');
        if (commonContent) commonContent.classList.remove('ide-active');

        const contentRight = document.querySelector('#content-body #content-right');
        if (contentRight) contentRight.classList.remove('ide-active');
    }
}

function runCode() {
    var code = editor.getValue();
    var inputText = input.value;
    var submissionId = 'none';
    var select = document.getElementById('language');
    var languageSelectedText = select.options[select.selectedIndex].text.toUpperCase();
    let resultLocked = false;

    terminal.value = "Running code...\n";
    document.querySelector('.ace_wrapper .submit-btn').classList.add('blur-disabled');

    fetch("/problem/run_code", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            language: languageSelectedText,
            source: code,
            stdin: inputText
        })
    })
    .then(function(response) {
        if (!response.ok) {
            return response.json().then(function(errorData) {
                throw new Error(errorData.detail);
            });
        }
        return response.json();
    })
    .then(function(data) {
        if (data.error) {
            terminal.textContent = "Error: " + data.error;
            return;
        }

        var channel = data.channel;
        submissionId = data.submission_id;
        var wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
        var wsHost = window.location.hostname;
        var wsPort = 15100;
        var ws = new WebSocket(wsProtocol + "://" + wsHost + ":" + wsPort + "/");

        ws.onopen = function() {
            ws.send(JSON.stringify({
                command: "set-filter",
                filter: [channel]
            }));
        };

        ws.onmessage = function(event) {
            var msg = JSON.parse(event.data);

            if (!resultLocked && msg.message.type == 'on_test_case_ide'){
                resultLocked = true;
                var resultData = msg.message.result.result;

                terminal.value = resultData.proc_output || "";
                if (resultData.error) terminal.value += "\nError: " + resultData.error;
                terminal.value += "\nElapsed Time: " + resultData.execution_time + "s";
                terminal.value += "\nMemory Usage: " + resultData.max_memory + " KB";
            } else if (!resultLocked && msg.message.type == 'on_test_case_ide2') {
                resultLocked = true;
                var resultData = msg.message.result;

                if (resultData.name === 'test-case-status' && resultData.cases && resultData.cases.length > 0) {
                    var testCase = resultData.cases[0]; // Lấy case đầu tiên

                    terminal.value = testCase.output || "";
                    terminal.value += "\nElapsed Time: " + testCase.time + "s";
                    terminal.value += "\nMemory Usage: " + testCase.memory + " KB";
                } else {
                    terminal.value = "Compile Error!";
                }
            } else if (msg.message.type == 'ide-compile-error') {
                ws.close();
                var compileLog = (msg.message.msg && msg.message.msg.log) ? msg.message.msg.log : "Unknown Compile Error!";
                terminal.value = "Compile Error:\n" + decodeAnsi(compileLog);
                resultLocked = false;
                deleteSubmission(submissionId);
                document.querySelector('.ace_wrapper .submit-btn').classList.remove('blur-disabled');
            } else if (msg.message.type == 'grading-end') {
                ws.close();
                resultLocked = false;
                deleteSubmission(submissionId);
                document.querySelector('.ace_wrapper .submit-btn').classList.remove('blur-disabled');
            }
        };

        ws.onerror = function() {
            terminal.value = "WebSocket connection error.";
        };
    })
    .catch(function(error) {
        terminal.value = "Error: " + error.message;
    });
}

function deleteSubmission(submissionId) {
    fetch("/submission/delete/", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": getCsrfToken()
        },
        body: `id=${submissionId}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            return;
        } else {
            console.warn(`⚠️ Failed to delete submission ${submissionId}:`, data.error || data.message);
        }
    })
    .catch(error => {
        console.error(`❌ Error deleting submission ${submissionId}:`, error);
    });
}

function getCsrfToken() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
}

function decodeAnsi(str) {
    return str
        .replace(/\u001b\[[0-9;]*m/g, '') // Xóa mã màu ANSI
        .replace(/\u001b\[K/g, '')        // Xóa ký tự xóa dòng
        .replace(/\r/g, '')               // Xóa \r thừa
        .replace(/\n{2,}/g, '\n');         // Gộp nhiều dòng trống lại thành 1
}

function formatCompileLog(log) {
    return `=== Compile Error ===\n\n${log.trim()}`;
}

function submitProblem() {
    let sourceCode = editor.getValue();
    var selectedLang = document.getElementById("language").value;

    var languageMap = {
        "c": 5,
        "cpp": 4,
        "java": 18,
        "kotlin": 15,
        "pascal": 7,
        "pypy": 16,
        "python": 9
    };

    var backendLanguageId = languageMap[selectedLang];
    if (!backendLanguageId) {
        terminal.value = "Ngôn ngữ không hợp lệ!";
        return;
    }

    document.getElementById("ide_source").value = sourceCode;

    var ideLanguageSelect = document.getElementById("ide_language");
    ideLanguageSelect.innerHTML = '';
    var option = document.createElement("option");
    option.value = backendLanguageId;
    option.selected = true;
    ideLanguageSelect.appendChild(option);

    var currentPath = window.location.pathname;
    if (!currentPath.endsWith('/')) {
        currentPath += '/';
    }
    var submitPath = currentPath + 'submit';
    document.getElementById("ide_submit_form").action = submitPath;
    const form = document.getElementById("ide_submit_form");
    form.submit();
}

function overrideJoinConfirm() {
    const joinButtons = document.querySelectorAll('.first-join, .participate-button.join-warning');
    if (!joinButtons.length) return;

    joinButtons.forEach(joinButton => {
        $(joinButton).off('click');

        joinButton.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopImmediatePropagation();

            const form = joinButton.closest('form');
            if (form) form.submit();
        }, true);
    });
}

document.addEventListener('DOMContentLoaded', function () {
    overrideJoinConfirm();
});