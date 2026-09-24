
(() => {
  'use strict';

  const SONGS = Array.isArray(window.KARAOKE_SONGS) ? window.KARAOKE_SONGS : [];
  const el = (id) => document.getElementById(id);
  const state = {
    songIndex: Math.max(0, Number(localStorage.getItem('karaoke.songIndex') || 0)),
    lineIndex: 0,
    player: null,
    playerReady: false,
    playerState: -1,
    mode: 'auto', // follow | auto | record
    targetIndex: 0,
    timer: null,
    mockTimer: null,
    mockTime: 0,
    mockDuration: 220,
    mediaMode: 'youtube', // youtube | local
    localObjectUrl: '',
    offset: 0,
    showReading: localStorage.getItem('karaoke.showReading') !== '0',
    showMeaning: localStorage.getItem('karaoke.showMeaning') !== '0',
    autoScroll: localStorage.getItem('karaoke.autoScroll') !== '0',
    statusTimer: null,
  };
  if (state.songIndex >= SONGS.length) state.songIndex = 0;

  const isMock = new URLSearchParams(location.search).get('test') === '1';
  const timingKey = (song) => `karaoke.timings.v4.${song.key}`;
  const offsetKey = (song) => `karaoke.offset.v4.${song.key}`;
  const learnedKey = (song) => `karaoke.learned.v2.${song.key}`;

  function song() { return SONGS[state.songIndex]; }
  function line() { return song()?.lines?.[state.lineIndex] || null; }

  function readJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || '') ?? fallback; } catch { return fallback; }
  }
  function storedTimingsFor(s = song()) {
    const stored = readJson(timingKey(s), null);
    return Array.isArray(stored) ? stored : null;
  }
  function timingsFor(s = song()) {
    const stored = storedTimingsFor(s);
    if (stored) return stored;
    return Array.isArray(s.timings) ? s.timings : [];
  }
  function saveTimings(values) {
    localStorage.setItem(timingKey(song()), JSON.stringify(values));
    renderLyrics();
    refreshModeButtons();
  }
  function learnedFor(s = song()) {
    const value = readJson(learnedKey(s), []);
    return new Set(Array.isArray(value) ? value : []);
  }
  function saveLearned(set) {
    localStorage.setItem(learnedKey(song()), JSON.stringify([...set].sort((a,b) => a-b)));
  }

  function fmtTime(value) {
    if (!Number.isFinite(value) || value < 0) return '--:--';
    const total = Math.floor(value);
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return `${min}:${String(sec).padStart(2, '0')}`;
  }

  function toast(message) {
    const node = el('toast');
    node.textContent = message;
    node.classList.add('show');
    clearTimeout(node._timer);
    node._timer = setTimeout(() => node.classList.remove('show'), 2200);
  }

  function setPlayerStatus(kind, text) {
    el('playerDot').className = `dot ${kind || ''}`.trim();
    el('playerStatus').textContent = text;
  }

  function videoUrl(s = song()) { return `https://www.youtube.com/watch?v=${encodeURIComponent(s.videoId)}`; }
  function biliUrl(s = song()) {
    const bvid = s?.backup?.bvid;
    return bvid ? `https://www.bilibili.com/video/${encodeURIComponent(bvid)}/` : '';
  }

  function usingLocal() { return state.mediaMode === 'local'; }

  function resetLocalAudio() {
    const audio = el('localAudio');
    if (audio) {
      try { audio.pause(); } catch {}
      audio.removeAttribute('src');
      try { audio.load(); } catch {}
      audio.hidden = true;
    }
    if (state.localObjectUrl) {
      URL.revokeObjectURL(state.localObjectUrl);
      state.localObjectUrl = '';
    }
    state.mediaMode = 'youtube';
    const playerNode = el('player');
    if (playerNode) playerNode.hidden = false;
  }

  function useLocalFile(file) {
    if (!file) return;
    resetLocalAudio();
    try {
      if (state.playerReady && state.player?.pauseVideo) state.player.pauseVideo();
    } catch {}
    const audio = el('localAudio');
    state.localObjectUrl = URL.createObjectURL(file);
    audio.src = state.localObjectUrl;
    audio.hidden = false;
    el('player').hidden = true;
    hidePlayerCover();
    state.mediaMode = 'local';
    setPlayerStatus('ready', `端末の音源：${file.name}`);
    audio.load();
    toast('端末の音源を読み込みました。ファイルはアップロードされません');
  }

  function showPlayerCover(title, body, isError = false) {
    const cover = el('playerCover');
    el('coverTitle').textContent = title;
    el('coverBody').textContent = body;
    const youtubeLink = el('coverYoutube');
    youtubeLink.href = videoUrl();
    const biliLink = el('coverBili');
    const b = biliUrl();
    biliLink.hidden = !b;
    if (b) biliLink.href = b;
    cover.hidden = false;
    setPlayerStatus(isError ? 'error' : '', isError ? '埋め込み再生を利用できません' : 'プレイヤーを準備中');
  }
  function hidePlayerCover() { el('playerCover').hidden = true; }

  function setCurrent(index, options = {}) {
    const max = Math.max(0, (song()?.lines?.length || 1) - 1);
    state.lineIndex = Math.min(max, Math.max(0, Number(index) || 0));
    localStorage.setItem(`karaoke.line.${song().key}`, String(state.lineIndex));
    renderNow();
    updateRowClasses();
    if (options.scroll !== false && state.autoScroll) scrollCurrent();
    if (options.seek) seekToLine(state.lineIndex);
  }

  function setTarget(index) {
    const max = Math.max(0, song().lines.length - 1);
    state.targetIndex = Math.min(max, Math.max(0, index));
    updateRowClasses();
    updateStickyButton();
  }

  function renderNow() {
    const current = line();
    const next = song()?.lines?.[state.lineIndex + 1];
    el('lineCounter').textContent = `${state.lineIndex + 1} / ${song().lines.length}`;
    el('nowOriginal').textContent = current?.o || '—';
    el('nowReading').textContent = current?.r || '';
    el('nowMeaning').textContent = current?.m || '';
    el('nextOriginal').textContent = next?.o || '曲の最後です';
    updateStickyButton();
  }

  function renderLyrics() {
    const list = el('lyricList');
    list.textContent = '';
    const timings = timingsFor();
    const learned = learnedFor();
    song().lines.forEach((item, index) => {
      const row = document.createElement('article');
      row.className = 'lyric-row';
      row.dataset.index = String(index);
      row.tabIndex = 0;
      row.setAttribute('role', 'button');
      row.setAttribute('aria-label', `${index + 1}行目へ移動`);
      if (learned.has(index)) row.classList.add('learned');

      const text = document.createElement('div');
      const original = document.createElement('div');
      original.className = 'lyric-original';
      original.lang = /[가-힣]/.test(item.o) ? 'ko' : 'en';
      original.textContent = item.o;
      const reading = document.createElement('div');
      reading.className = 'lyric-reading';
      reading.textContent = item.r;
      const meaning = document.createElement('div');
      meaning.className = 'lyric-meaning';
      meaning.textContent = item.m;
      text.append(original, reading, meaning);

      const meta = document.createElement('div');
      meta.className = 'lyric-meta';
      const time = document.createElement('time');
      time.className = 'lyric-time';
      time.textContent = Number.isFinite(timings[index]) ? fmtTime(timings[index]) : '未記録';
      const learn = document.createElement('button');
      learn.className = 'learn-button';
      learn.type = 'button';
      learn.textContent = learned.has(index) ? '✓' : '○';
      learn.title = learned.has(index) ? '覚えた印を外す' : '覚えた行にする';
      learn.setAttribute('aria-pressed', learned.has(index) ? 'true' : 'false');
      learn.addEventListener('click', (event) => {
        event.stopPropagation();
        const set = learnedFor();
        if (set.has(index)) set.delete(index); else set.add(index);
        saveLearned(set);
        renderLyrics();
      });
      meta.append(time, learn);
      row.append(text, meta);
      row.addEventListener('click', () => {
        setCurrent(index, { scroll: false, seek: state.mode !== 'record' });
        if (state.mode === 'record') setTarget(index);
      });
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          row.click();
        }
      });
      list.append(row);
    });
    updateRowClasses();
  }

  function updateRowClasses() {
    document.querySelectorAll('.lyric-row').forEach((row) => {
      const index = Number(row.dataset.index);
      row.classList.toggle('current', index === state.lineIndex);
      row.classList.toggle('target', state.mode === 'record' && index === state.targetIndex);
    });
  }

  function scrollCurrent() {
    requestAnimationFrame(() => {
      const row = document.querySelector(`.lyric-row[data-index="${state.lineIndex}"]`);
      row?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  function updateStickyButton() {
    const button = el('nextLineButton');
    const small = el('nextLineText');
    if (state.mode === 'record') {
      const target = song().lines[state.targetIndex];
      button.firstChild.textContent = 'この行が始まった';
      small.textContent = target?.o || '記録完了';
    } else {
      button.firstChild.textContent = '次の歌詞';
      small.textContent = song().lines[state.lineIndex + 1]?.o || '曲の最後';
    }
  }

  function renderSongSelector() {
    const select = el('songSelect');
    select.textContent = '';
    SONGS.forEach((s, index) => {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = s.title;
      select.append(option);
    });
    select.value = String(state.songIndex);
  }

  function changeSong(index) {
    resetLocalAudio();
    state.songIndex = Math.min(SONGS.length - 1, Math.max(0, Number(index) || 0));
    localStorage.setItem('karaoke.songIndex', String(state.songIndex));
    el('songSelect').value = String(state.songIndex);
    state.lineIndex = Math.min(song().lines.length - 1, Math.max(0, Number(localStorage.getItem(`karaoke.line.${song().key}`) || 0)));
    state.targetIndex = 0;
    state.offset = Number(localStorage.getItem(offsetKey(song())) || 0);
    el('offsetOutput').textContent = `${state.offset >= 0 ? '+' : ''}${state.offset.toFixed(2)}秒`;
    el('sourceTitle').textContent = song().sourceTitle || song().title;
    el('openYoutube').href = videoUrl();
    const b = biliUrl();
    el('openBili').hidden = !b;
    if (b) el('openBili').href = b;
    renderLyrics();
    renderNow();
    loadVideo(song().videoId);
    if (state.mode !== 'record') state.mode = canAuto() ? 'auto' : 'follow';
    refreshModeButtons();
  }

  function currentTime() {
    if (isMock) return state.mockTime;
    if (usingLocal()) return Number(el('localAudio')?.currentTime);
    if (!state.playerReady || !state.player || typeof state.player.getCurrentTime !== 'function') return NaN;
    try { return Number(state.player.getCurrentTime()); } catch { return NaN; }
  }
  function duration() {
    if (isMock) return state.mockDuration;
    if (usingLocal()) return Number(el('localAudio')?.duration);
    if (!state.playerReady || !state.player || typeof state.player.getDuration !== 'function') return NaN;
    try { return Number(state.player.getDuration()); } catch { return NaN; }
  }

  function playPause() {
    if (isMock) {
      if (state.mockTimer) stopMock(); else startMock();
      return;
    }
    if (usingLocal()) {
      const audio = el('localAudio');
      if (!audio?.src) { toast('端末の音源を選んでください'); return; }
      if (audio.paused) audio.play().catch(() => toast('再生できませんでした')); else audio.pause();
      return;
    }
    if (!state.playerReady) { toast('プレイヤーの準備を待っています'); return; }
    try {
      const p = state.player.getPlayerState();
      if (p === 1) state.player.pauseVideo(); else state.player.playVideo();
    } catch { toast('再生操作に失敗しました'); }
  }
  function startMock() {
    if (state.mockTimer) return;
    state.playerState = 1;
    state.mockTimer = setInterval(() => { state.mockTime += .1; if (state.mockTime >= state.mockDuration) stopMock(); }, 100);
    el('playButton').textContent = '⏸';
  }
  function stopMock() {
    clearInterval(state.mockTimer); state.mockTimer = null; state.playerState = 2; el('playButton').textContent = '▶';
  }
  function seek(seconds) {
    if (!Number.isFinite(seconds)) return;
    if (isMock) { state.mockTime = Math.max(0, Math.min(state.mockDuration, seconds)); return; }
    if (usingLocal()) {
      const audio = el('localAudio');
      if (audio) audio.currentTime = Math.max(0, Math.min(Number.isFinite(audio.duration) ? audio.duration : seconds, seconds));
      return;
    }
    if (!state.playerReady) return;
    try { state.player.seekTo(Math.max(0, seconds), true); } catch {}
  }
  function seekBy(delta) { const t = currentTime(); if (Number.isFinite(t)) seek(t + delta); }
  function seekToLine(index) {
    const timings = timingsFor();
    if (Number.isFinite(timings[index])) seek(timings[index] - state.offset);
    else toast('この行の時刻はまだ記録されていません');
  }

  function recordedCount() { return timingsFor().filter(Number.isFinite).length; }
  function canAuto() { return recordedCount() >= 2; }

  function setMode(mode) {
    if (mode === 'auto' && !canAuto()) {
      toast('この曲には自動追従の時刻がありません');
      openHelp('record');
      return;
    }
    state.mode = mode;
    if (mode === 'record') {
      const timings = timingsFor();
      const firstMissing = timings.findIndex((value) => !Number.isFinite(value));
      setTarget(firstMissing >= 0 ? firstMissing : 0);
      el('recordBanner').hidden = false;
    } else {
      el('recordBanner').hidden = true;
    }
    refreshModeButtons();
    updateRowClasses();
    updateStickyButton();
  }

  function refreshModeButtons() {
    ['follow','auto','record'].forEach((name) => {
      const button = el(`${name}Mode`);
      button.classList.toggle('active', state.mode === name);
      button.setAttribute('aria-pressed', state.mode === name ? 'true' : 'false');
    });
    el('autoMode').disabled = !canAuto();
    const customized = Boolean(storedTimingsFor());
    el('timingStatus').textContent = customized ? 'この端末の修正版' : '内蔵タイミング';
    el('recordedCount').textContent = `${recordedCount()} / ${song().lines.length} 行`;
  }

  function markTargetNow() {
    const t = currentTime();
    if (!Number.isFinite(t)) { toast('先に動画を再生してください'); return; }
    const values = timingsFor().slice();
    while (values.length < song().lines.length) values.push(null);
    values[state.targetIndex] = Math.max(0, Number((t + state.offset).toFixed(2)));
    const marked = state.targetIndex;
    saveTimings(values);
    setCurrent(marked, { scroll: true });
    if (marked < song().lines.length - 1) setTarget(marked + 1);
    else { toast('最後の行まで記録しました'); setMode('auto'); }
  }

  function autoTick() {
    const t = currentTime();
    const d = duration();
    el('timeDisplay').textContent = `${fmtTime(t)} / ${fmtTime(d)}`;
    if (state.mode !== 'auto' || !Number.isFinite(t)) return;
    const adjusted = t + state.offset;
    const timings = timingsFor();
    let match = -1;
    for (let i = 0; i < timings.length; i += 1) {
      if (Number.isFinite(timings[i]) && timings[i] <= adjusted) match = i;
      if (Number.isFinite(timings[i]) && timings[i] > adjusted) break;
    }
    if (match < 0) match = 0;
    if (match !== state.lineIndex) setCurrent(match, { scroll: true });
  }

  function loadVideo(videoId) {
    el('player').hidden = false;
    el('localAudio').hidden = true;
    state.mediaMode = 'youtube';
    showPlayerCover('動画を読み込んでいます', 'YouTubeの再生ボタンが出るまで少し待ってください。歌詞は先に操作できます。');
    state.playerReady = false;
    clearTimeout(state.statusTimer);
    state.statusTimer = setTimeout(() => {
      if (!state.playerReady) showPlayerCover('動画を埋め込めませんでした', 'YouTubeで開くか、端末にある音源を選べば、このページの自動追従をそのまま使えます。', true);
    }, 12000);

    if (isMock) {
      state.mockTime = 0;
      state.mockDuration = 220;
      state.playerReady = true;
      hidePlayerCover();
      setPlayerStatus('ready', 'テストプレイヤー準備完了');
      return;
    }
    if (state.player && typeof state.player.cueVideoById === 'function') {
      try {
        state.player.cueVideoById({ videoId, startSeconds: 0 });
        state.playerReady = true;
        hidePlayerCover();
        setPlayerStatus('ready', '再生できます');
        return;
      } catch {}
    }
    createPlayer(videoId);
  }

  function createPlayer(videoId) {
    if (!window.YT || typeof window.YT.Player !== 'function') return;
    try {
      state.player = new window.YT.Player('player', {
        host: 'https://www.youtube-nocookie.com',
        videoId,
        playerVars: {
          playsinline: 1,
          controls: 1,
          rel: 0,
          fs: 1,
          modestbranding: 1,
          origin: location.origin,
        },
        events: {
          onReady: (event) => {
            state.playerReady = true;
            clearTimeout(state.statusTimer);
            try { event.target.pauseVideo(); } catch {}
            hidePlayerCover();
            setPlayerStatus('ready', '再生できます');
          },
          onStateChange: (event) => {
            state.playerState = event.data;
            el('playButton').textContent = event.data === 1 ? '⏸' : '▶';
          },
          onError: (event) => {
            state.playerReady = false;
            showPlayerCover('この動画はページ内で再生できません', `YouTubeエラー ${event.data}。YouTubeで開くボタンを使ってください。`, true);
          },
        },
      });
    } catch {
      showPlayerCover('プレイヤーの作成に失敗しました', 'YouTubeで開くボタンから再生してください。', true);
    }
  }

  window.onYouTubeIframeAPIReady = () => createPlayer(song().videoId);

  function loadYoutubeApi() {
    if (isMock) { loadVideo(song().videoId); return; }
    if (window.YT?.Player) { createPlayer(song().videoId); return; }
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    script.onerror = () => showPlayerCover('YouTubeプレイヤーを読み込めません', '通信を確認して、YouTubeで開くボタンを使ってください。', true);
    document.head.append(script);
  }

  function toggleDisplay(type) {
    if (type === 'reading') {
      state.showReading = !state.showReading;
      localStorage.setItem('karaoke.showReading', state.showReading ? '1' : '0');
    } else {
      state.showMeaning = !state.showMeaning;
      localStorage.setItem('karaoke.showMeaning', state.showMeaning ? '1' : '0');
    }
    applyDisplay();
  }
  function applyDisplay() {
    document.body.classList.toggle('hide-reading', !state.showReading);
    document.body.classList.toggle('hide-meaning', !state.showMeaning);
    el('toggleReading').classList.toggle('active', state.showReading);
    el('toggleMeaning').classList.toggle('active', state.showMeaning);
    el('toggleReading').setAttribute('aria-pressed', state.showReading ? 'true' : 'false');
    el('toggleMeaning').setAttribute('aria-pressed', state.showMeaning ? 'true' : 'false');
  }

  function adjustOffset(delta) {
    state.offset = Math.max(-10, Math.min(10, Number((state.offset + delta).toFixed(2))));
    localStorage.setItem(offsetKey(song()), String(state.offset));
    el('offsetOutput').textContent = `${state.offset >= 0 ? '+' : ''}${state.offset.toFixed(2)}秒`;
  }

  function exportTimings() {
    const payload = {
      format: 'korean-karaoke-timings-v4',
      songKey: song().key,
      videoId: song().videoId,
      title: song().title,
      timings: timingsFor(),
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${song().key}-timings.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function importTimings(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(String(reader.result));
        if (!Array.isArray(data.timings)) throw new Error('timingsなし');
        const values = data.timings.slice(0, song().lines.length).map((x) => Number.isFinite(Number(x)) ? Number(x) : null);
        while (values.length < song().lines.length) values.push(null);
        saveTimings(values);
        toast('時刻データを読み込みました');
      } catch { toast('このファイルは読み込めません'); }
    };
    reader.readAsText(file);
  }

  function clearTimings() {
    if (!confirm(`${song().title} で自分が直した時刻を消して、内蔵タイミングに戻しますか？`)) return;
    localStorage.removeItem(timingKey(song()));
    setMode(canAuto() ? 'auto' : 'follow');
    renderLyrics();
    refreshModeButtons();
    toast('内蔵タイミングに戻しました');
  }

  function openHelp(topic = 'main') {
    const dialog = el('helpDialog');
    const title = el('helpTitle');
    const body = el('helpBody');
    if (topic === 'record') {
      title.textContent = '行の時刻を直す方法';
      body.innerHTML = `
        <ol>
          <li>直したい歌詞行をタップします。黄色い点線が付きます。</li>
          <li>曲を少し前から再生します。</li>
          <li>その行が歌い始めた瞬間に、画面下の「この行が始まった」を押します。</li>
          <li>修正はこの端末だけに保存され、次回から自動追従へ反映されます。</li>
        </ol>
        <p>全体が同じだけ早い・遅い場合は、行ごとに直さず「歌詞 ±0.25秒」を使うほうが速いです。High Quality版とPreview V2の修正は別々に保存されます。</p>`;
    } else {
      title.textContent = '使い方';
      body.innerHTML = `
        <p><strong>自動追従</strong>は最初から使えます。時刻はページ内に固定で入っているため、「同期データの取得」を待つ必要はありません。</p>
        <p>内蔵時刻は公開動画の自動字幕にある実時刻を歌詞順に照合し、字幕が欠けた行だけを前後の時刻から補っています。曲によっては少しズレるため、全体補正と行ごとの修正を残しています。</p>
        <p>歌詞行をタップすると、その位置へ移動します。<strong>手動送り</strong>では画面下のボタンで自分のペースに合わせられます。</p>
        <p>YouTubeをページ内で再生できない場合は、<strong>端末の音源を使う</strong>を選べます。選んだファイルは端末内だけで再生され、アップロードされません。</p>
        <p>このページには広告やアクセス解析を入れていません。YouTube再生時のみYouTubeへ接続します。</p>`;
    }
    dialog.hidden = false;
  }

  function closeHelp() { el('helpDialog').hidden = true; }

  function bind() {
    el('songSelect').addEventListener('change', (event) => changeSong(event.target.value));
    const chooseLocal = () => el('localFile').click();
    el('localFileButton').addEventListener('click', chooseLocal);
    el('coverLocal').addEventListener('click', chooseLocal);
    el('localFile').addEventListener('change', (event) => {
      const file = event.target.files?.[0];
      if (file) useLocalFile(file);
      event.target.value = '';
    });
    const localAudio = el('localAudio');
    localAudio.addEventListener('play', () => { el('playButton').textContent = '⏸'; setPlayerStatus('ready', '端末の音源を再生中'); });
    localAudio.addEventListener('pause', () => { el('playButton').textContent = '▶'; if (usingLocal()) setPlayerStatus('ready', '端末の音源'); });
    localAudio.addEventListener('ended', () => { el('playButton').textContent = '▶'; });
    localAudio.addEventListener('error', () => toast('この音源ファイルは再生できません'));
    el('playButton').addEventListener('click', playPause);
    el('back5').addEventListener('click', () => seekBy(-5));
    el('forward5').addEventListener('click', () => seekBy(5));
    el('prevLine').addEventListener('click', () => setCurrent(state.lineIndex - 1));
    el('nextLine').addEventListener('click', () => setCurrent(state.lineIndex + 1));
    el('stickyPrev').addEventListener('click', () => setCurrent(state.lineIndex - 1));
    el('stickyNext').addEventListener('click', () => setCurrent(state.lineIndex + 1));
    el('nextLineButton').addEventListener('click', () => {
      if (state.mode === 'record') markTargetNow();
      else setCurrent(state.lineIndex + 1);
    });
    el('followMode').addEventListener('click', () => setMode('follow'));
    el('autoMode').addEventListener('click', () => setMode('auto'));
    el('recordMode').addEventListener('click', () => setMode('record'));
    el('toggleReading').addEventListener('click', () => toggleDisplay('reading'));
    el('toggleMeaning').addEventListener('click', () => toggleDisplay('meaning'));
    el('toggleScroll').addEventListener('click', () => {
      state.autoScroll = !state.autoScroll;
      localStorage.setItem('karaoke.autoScroll', state.autoScroll ? '1' : '0');
      el('toggleScroll').classList.toggle('active', state.autoScroll);
      toast(state.autoScroll ? '自動スクロールをオンにしました' : '自動スクロールをオフにしました');
    });
    el('offsetMinus').addEventListener('click', () => adjustOffset(-.25));
    el('offsetPlus').addEventListener('click', () => adjustOffset(.25));
    el('exportTimings').addEventListener('click', exportTimings);
    el('importButton').addEventListener('click', () => el('importFile').click());
    el('importFile').addEventListener('change', (event) => importTimings(event.target.files?.[0]));
    el('clearTimings').addEventListener('click', clearTimings);
    el('helpButton').addEventListener('click', () => openHelp());
    el('recordHelp').addEventListener('click', () => openHelp('record'));
    el('closeHelp').addEventListener('click', closeHelp);
    el('helpDialog').addEventListener('click', (event) => { if (event.target === el('helpDialog')) closeHelp(); });
    document.addEventListener('keydown', (event) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      if (event.key === 'ArrowRight') setCurrent(state.lineIndex + 1);
      if (event.key === 'ArrowLeft') setCurrent(state.lineIndex - 1);
      if (event.code === 'Space') { event.preventDefault(); playPause(); }
      if (event.key.toLowerCase() === 'm' && state.mode === 'record') markTargetNow();
    });
  }

  function init() {
    if (!SONGS.length) {
      document.body.innerHTML = '<main style="padding:2rem;color:white">歌詞データを読み込めませんでした。</main>';
      return;
    }
    renderSongSelector();
    bind();
    applyDisplay();
    el('toggleScroll').classList.toggle('active', state.autoScroll);
    el('offsetOutput').textContent = `${state.offset >= 0 ? '+' : ''}${state.offset.toFixed(2)}秒`;
    changeSong(state.songIndex);
    setMode(canAuto() ? 'auto' : 'follow');
    state.timer = setInterval(autoTick, 150);
    loadYoutubeApi();
  }

  window.addEventListener('beforeunload', () => { if (state.localObjectUrl) URL.revokeObjectURL(state.localObjectUrl); });
  document.addEventListener('DOMContentLoaded', init);
})();
