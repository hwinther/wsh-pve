/*
 * The Windows sound backend of the 3dfx programs (wshspace, wshdemo): WinMM waveOut, 16-bit stereo
 * at 22050 Hz in four buffers of 1024 frames, polled (no callback, no thread): plat_audio_tick()
 * refills and resubmits each buffer the device has finished with. WINMM.DLL is loaded at run time,
 * so the program imports KERNEL32, USER32 and GDI32 only and runs silently without it. Included by
 * the program's plat_win.c after w3d.h, which defines SND_MIX(pcm, frames, rate) to its mixer first.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_SND_WIN_H
#define WSH_SND_WIN_H

#define AUD_RATE 22050
#define AUD_FRAMES 1024
#define AUD_BUFS 4

typedef struct {
	uint16_t wFormatTag, nChannels;
	uint32_t nSamplesPerSec, nAvgBytesPerSec;
	uint16_t nBlockAlign, wBitsPerSample, cbSize;
} WFX;

typedef struct wvhdr {
	char *lpData;
	uint32_t dwBufferLength, dwBytesRecorded;
	uintptr_t dwUser;
	uint32_t dwFlags, dwLoops;
	struct wvhdr *lpNext;
	uintptr_t reserved;
} WVHDR;

static HMODULE winmm;
static void *hwave;
static WVHDR whdr[AUD_BUFS];
static int16_t wbuf[AUD_BUFS][AUD_FRAMES * 2];
static int aud_on;
static uint32_t(WINAPI *p_waveOutOpen)(void **, UINT, const WFX *, uintptr_t, uintptr_t, DWORD);
static uint32_t(WINAPI *p_waveOutPrepareHeader)(void *, WVHDR *, UINT);
static uint32_t(WINAPI *p_waveOutUnprepareHeader)(void *, WVHDR *, UINT);
static uint32_t(WINAPI *p_waveOutWrite)(void *, WVHDR *, UINT);
static uint32_t(WINAPI *p_waveOutReset)(void *);
static uint32_t(WINAPI *p_waveOutClose)(void *);

void plat_audio_init(int enable)
{
	if (!enable || aud_on)
		return;
	winmm = LoadLibraryA("WINMM.DLL");
	if (!winmm)
		return;
	*(FARPROC *)&p_waveOutOpen = GetProcAddress(winmm, "waveOutOpen");
	*(FARPROC *)&p_waveOutPrepareHeader = GetProcAddress(winmm, "waveOutPrepareHeader");
	*(FARPROC *)&p_waveOutUnprepareHeader = GetProcAddress(winmm, "waveOutUnprepareHeader");
	*(FARPROC *)&p_waveOutWrite = GetProcAddress(winmm, "waveOutWrite");
	*(FARPROC *)&p_waveOutReset = GetProcAddress(winmm, "waveOutReset");
	*(FARPROC *)&p_waveOutClose = GetProcAddress(winmm, "waveOutClose");
	if (!p_waveOutOpen || !p_waveOutPrepareHeader || !p_waveOutWrite || !p_waveOutReset || !p_waveOutClose)
		return;
	WFX fmt = {1, 2, AUD_RATE, AUD_RATE * 4, 4, 16, 0};
	if (p_waveOutOpen(&hwave, (UINT)-1, &fmt, 0, 0, 0) != 0)
		return;
	for (int i = 0; i < AUD_BUFS; i++) {
		memset(&whdr[i], 0, sizeof(WVHDR));
		whdr[i].lpData = (char *)wbuf[i];
		whdr[i].dwBufferLength = AUD_FRAMES * 4;
		p_waveOutPrepareHeader(hwave, &whdr[i], sizeof(WVHDR));
		whdr[i].dwFlags |= 1U; /* WHDR_DONE so first tick fills & submits */
	}
	aud_on = 1;
}

void plat_audio_tick(void)
{
	if (!aud_on)
		return;
	for (int i = 0; i < AUD_BUFS; i++) {
		if (whdr[i].dwFlags & 1U) {
			whdr[i].dwFlags &= ~1U;
			SND_MIX(wbuf[i], AUD_FRAMES, AUD_RATE);
			p_waveOutWrite(hwave, &whdr[i], sizeof(WVHDR));
		}
	}
}

void plat_audio_close(void)
{
	if (aud_on) {
		p_waveOutReset(hwave);
		for (int i = 0; i < AUD_BUFS; i++)
			if (p_waveOutUnprepareHeader)
				p_waveOutUnprepareHeader(hwave, &whdr[i], sizeof(WVHDR));
		p_waveOutClose(hwave);
		hwave = NULL;
		aud_on = 0;
	}
	if (winmm) {
		FreeLibrary(winmm);
		winmm = NULL;
	}
}

#endif
