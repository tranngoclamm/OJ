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
    let code = editor.getValue(); 
    let inputText = input.value;  
    const select = document.getElementById('language');
    const languageSelectedText = select.options[select.selectedIndex].text.toUpperCase();
    terminal.value = "Running code...\n";
    showTab('output-tab');
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
    .then(response => {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.detail); 
            });
        }
        return response.json();  
    })
    .then(data => {
        if (data.error) {
            terminal.textContent = "Error: " + data.error;
            return;
        }

        const channel = data.channel;
        const ws = new WebSocket("ws://127.0.0.1:15100/");

        ws.onopen = () => {
            ws.send(JSON.stringify({
                command: "set-filter",
                filter: [channel]
            }));
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);

            if (msg.message.type == 'on_test_case_ide'){
                ws.close();
                const resultData = msg.message.result.result;

                terminal.value = resultData.proc_output || "";
                if (resultData.error) terminal.value += "\nError: " + resultData.error;
                terminal.value += `\nElapsed Time: ${resultData.execution_time}s`;
                terminal.value += `\nMemory Usage: ${resultData.max_memory} KB`;
                document.querySelector('.ace_wrapper .submit-btn').classList.remove('blur-disabled');
            } else if (msg.message.type == 'on_test_case_ide2') {
                ws.close();
                const resultData = msg.message.result;
            
                if (resultData.name === 'test-case-status' && resultData.cases && resultData.cases.length > 0) {
                    const testCase = resultData.cases[0]; // Lấy case đầu tiên
            
                    terminal.value = testCase.output || "";            
                    terminal.value += `\nElapsed Time: ${testCase.time}s`;
                    terminal.value += `\nMemory Usage: ${testCase.memory} KB`;
                } else {
                    terminal.value = "Compile Error!";
                }
                document.querySelector('.ace_wrapper .submit-btn').classList.remove('blur-disabled');

            } else if (msg.message.type == 'ide-compile-error') {
                ws.close();
                const compileLog = msg.message.msg?.log || "Unknown Compile Error!";
                terminal.value = "Compile Error:\n" + decodeAnsi(compileLog);
                document.querySelector('.ace_wrapper .submit-btn').classList.remove('blur-disabled');
            }
        };

        ws.onerror = () => {
            terminal.value = "WebSocket connection error.";
        };
    })
    .catch(error => {
        terminal.value = "Error: " + error.message;  
    });
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
    if (!confirm("Bạn có chắc chắn muốn nộp bài không?")) {
        return; // Người dùng chọn "Không"
    }

    // Lấy source code từ editor2 (ACE Editor)
    let sourceCode = editor.getValue(); 

    // Lấy ngôn ngữ từ dropdown
    var selectedLang = document.getElementById("language").value;

    // Map từ ngôn ngữ IDE sang id ngôn ngữ database
    var languageMap = {
        "c": 5,
        "cpp": 14,
        "java": 18,
        "kotlin": 15,
        "pascal": 7,
        "pypy": 16,
        "python": 9
    };

    var backendLanguageId = languageMap[selectedLang];

    if (!backendLanguageId) {
        alert("Ngôn ngữ không hợp lệ!");
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
    document.querySelector("#ide_submit_form button[type='submit']").click();
}
