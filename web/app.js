const button = document.querySelector('#speak');
const player = document.querySelector('#player');
const speed = document.querySelector('#speed');
const status = document.querySelector('#status');
const text = document.querySelector('#text');
const voice = document.querySelector('#voice');

async function loadVoices() {
  const response = await fetch('/api/voices');
  if (!response.ok) throw new Error('Không tải được danh sách giọng đọc.');
  const { voices } = await response.json();
  voice.innerHTML = voices.map((name) => `<option value="${name}" ${name === 'khanh_vy' ? 'selected' : ''}>${name.replace('_', ' ')}</option>`).join('');
  status.textContent = 'Sẵn sàng tạo giọng nói.';
}

button.addEventListener('click', async () => {
  const value = text.value.trim();
  if (!value) { status.textContent = 'Vui lòng nhập nội dung.'; return; }
  button.disabled = true;
  player.hidden = true;
  status.textContent = 'Đang tạo giọng nói — lần đầu có thể mất thời gian tải model…';
  try {
    const response = await fetch('/api/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: value, voice: voice.value, speed: Number(speed.value) }),
    });
    if (!response.ok) throw new Error((await response.json()).error || 'Không thể tạo giọng nói.');
    const previous = player.src;
    player.src = URL.createObjectURL(await response.blob());
    if (previous.startsWith('blob:')) URL.revokeObjectURL(previous);
    player.hidden = false;
    await player.play();
    status.textContent = 'Hoàn tất. Bạn có thể nghe hoặc tải file WAV từ trình phát.';
  } catch (error) {
    status.textContent = `Lỗi: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

loadVoices().catch((error) => { status.textContent = `Lỗi: ${error.message}`; });
