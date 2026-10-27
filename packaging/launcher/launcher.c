/* LTH Overlays launcher: starts python\pythonw.exe app\<SCRIPT> from its own folder.
 * Tiny, no network, no registry, no admin rights - nothing that antivirus heuristics dislike. */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>

#ifndef SCRIPT
#define SCRIPT L"run.py"
#endif
#ifndef PYEXE
#define PYEXE L"pythonw.exe"
#endif
#ifndef EXTRA
#define EXTRA L""
#endif

static int run(void) {
    wchar_t dir[MAX_PATH], py[MAX_PATH], script[MAX_PATH];
    GetModuleFileNameW(NULL, dir, MAX_PATH);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;
    swprintf(py, MAX_PATH, L"%ls\\python\\%ls", dir, PYEXE);
    swprintf(script, MAX_PATH, L"%ls\\app\\%ls", dir, SCRIPT);
    if (GetFileAttributesW(py) == INVALID_FILE_ATTRIBUTES || GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL, L"The \"python\" and \"app\" folders were not found next to this program.\n"
                          L"Extract the whole zip, not only the .exe file.", L"LTH Overlays", MB_ICONERROR);
        return 1;
    }
    static wchar_t cmd[32768];
    LPWSTR args = GetCommandLineW();
    /* skip our own exe path in the command line */
    if (*args == L'"') { args++; while (*args && *args != L'"') args++; if (*args) args++; }
    else { while (*args && *args != L' ') args++; }
    while (*args == L' ') args++;
    swprintf(cmd, 32768, L"\"%ls\" -E -s -X utf8 \"%ls\" %ls %ls", py, script, EXTRA, args);
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si); si.cb = sizeof si; ZeroMemory(&pi, sizeof pi);
    SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
    if (!CreateProcessW(py, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"Could not start Python.", L"LTH Overlays", MB_ICONERROR);
        return 1;
    }
#ifdef CONSOLE
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0; GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return (int)code;
#else
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return 0;
#endif
}

#ifdef CONSOLE
int wmain(void) { return run(); }
#else
int WINAPI wWinMain(HINSTANCE h, HINSTANCE p, PWSTR a, int show) { return run(); }
#endif
