import React, { useState, useEffect } from 'react';
import { Settings, Cookie, Clock, Share2, Lock, Save, CheckCircle2 } from 'lucide-react';

export default function SettingsTab({ settings, onSaveCookie, onSaveDailyRate, onSaveAutopostTimes, onSaveSocialDefaults }) {
  const [cookie, setCookie] = useState(settings.cookie || '');
  const [dailyRate, setDailyRate] = useState(settings.daily_post_rate || 2);
  const [timeSlots, setTimeSlots] = useState(settings.times || ['12:00', '18:00']);

  // Redes Sociais e Privacidade Padrão
  const [postYoutube, setPostYoutube] = useState(settings.default_post_youtube !== false);
  const [postShorts, setPostShorts] = useState(settings.default_post_shorts !== false);
  const [postTiktok, setPostTiktok] = useState(settings.default_post_tiktok !== false);
  const [tiktokPrivacy, setTiktokPrivacy] = useState(settings.default_tiktok_privacy || 'PUBLIC');

  const [savingCookie, setSavingCookie] = useState(false);
  const [savingTimes, setSavingTimes] = useState(false);
  const [savingSocial, setSavingSocial] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState('');

  useEffect(() => {
    setCookie(settings.cookie || '');
    setDailyRate(settings.daily_post_rate || 2);
    setTimeSlots(settings.times || ['12:00', '18:00']);
  }, [settings]);

  // Atualiza as caixas de horário quando o ritmo diário muda
  const handleRateChange = (newRate) => {
    const rateNum = parseInt(newRate, 10);
    setDailyRate(rateNum);
    
    let defaultTimes = ['18:00'];
    if (rateNum === 2) defaultTimes = ['12:00', '18:00'];
    if (rateNum === 3) defaultTimes = ['10:00', '15:00', '20:00'];

    let current = [...timeSlots];
    while (current.length < rateNum) {
      current.push(defaultTimes[current.length] || '18:00');
    }
    setTimeSlots(current.slice(0, rateNum));
    onSaveDailyRate(rateNum);
  };

  const handleTimeSlotChange = (index, value) => {
    const updated = [...timeSlots];
    updated[index] = value;
    setTimeSlots(updated);
  };

  const handleSaveCookieSubmit = async (e) => {
    e.preventDefault();
    setSavingCookie(true);
    await onSaveCookie(cookie);
    setSavingCookie(false);
    setSavedSuccess('Cookie do Douyin salvo no .env e sincronizado com sucesso!');
    setTimeout(() => setSavedSuccess(''), 4000);
  };

  const handleSaveTimesSubmit = async (e) => {
    e.preventDefault();
    setSavingTimes(true);
    await onSaveAutopostTimes(timeSlots);
    setSavingTimes(false);
    setSavedSuccess('Horários de autoposting salvos com sucesso!');
    setTimeout(() => setSavedSuccess(''), 4000);
  };

  const handleSaveSocialSubmit = async (e) => {
    e.preventDefault();
    setSavingSocial(true);
    if (onSaveSocialDefaults) {
      await onSaveSocialDefaults({
        postYoutube,
        postShorts,
        postTiktok,
        tiktokPrivacy
      });
    }
    setSavingSocial(false);
    setSavedSuccess('Padrões de Redes Sociais e Privacidade salvos!');
    setTimeout(() => setSavedSuccess(''), 4000);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="section-header">
        <h2 className="section-title">
          <Settings className="w-6 h-6 text-cyan-400" />
          <span>⚙️ Central de Configurações</span>
        </h2>
      </div>

      {savedSuccess && (
        <div style={{ background: 'rgba(46,125,50,0.15)', border: '1px solid rgba(76,175,80,0.4)', color: '#a5d6a7', padding: '14px 20px', borderRadius: 'var(--radius-md)', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <CheckCircle2 className="w-5 h-5 text-green-400" />
          <span>{savedSuccess}</span>
        </div>
      )}

      {/* 1. SEÇÃO DE COOKIE */}
      <div className="settings-card">
        <h3 className="settings-card-title">
          <Cookie className="w-5 h-5 text-amber-400" />
          <span>🍪 Autenticação & Cookie do Douyin</span>
        </h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', marginBottom: '16px' }}>
          Cole o cookie extraído do navegador para autenticação do scraper. Ele será salvo no arquivo <code>.env</code> e sincronizado automaticamente com a API local.
        </p>

        <form onSubmit={handleSaveCookieSubmit}>
          <div className="form-group">
            <label className="form-label">Valor do DOUYIN_COOKIE:</label>
            <textarea
              className="form-textarea"
              rows={4}
              value={cookie}
              onChange={(e) => setCookie(e.target.value)}
              placeholder="enter_pc_once=1; UIFID_TEMP=..."
              required
              style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={savingCookie}>
            <Save className="w-4 h-4" />
            <span>{savingCookie ? 'Salvando e Sincronizando...' : '💾 Salvar e Sincronizar Cookie'}</span>
          </button>
        </form>
      </div>

      {/* 2. SEÇÃO DE RITMO E HORÁRIOS */}
      <div className="settings-card">
        <h3 className="settings-card-title">
          <Clock className="w-5 h-5 text-blue-400" />
          <span>⏰ Ritmo Diário & Horários Fixos de Autoposting</span>
        </h3>

        <form onSubmit={handleSaveTimesSubmit}>
          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label className="form-label">Ritmo Diário de Postagens:</label>
            <select 
              className="form-select" 
              value={dailyRate} 
              onChange={(e) => handleRateChange(e.target.value)}
            >
              <option value={1}>1 vídeo por dia</option>
              <option value={2}>2 vídeos por dia (Recomendado)</option>
              <option value={3}>3 vídeos por dia</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Horários Fixos ({dailyRate} caixas):</label>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${dailyRate}, 1fr)`, gap: '12px' }}>
              {timeSlots.map((time, idx) => (
                <div key={idx}>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-subtle)', display: 'block', marginBottom: '4px' }}>
                    Postagem #{idx + 1}
                  </span>
                  <input
                    type="time"
                    className="form-input"
                    value={time}
                    onChange={(e) => handleTimeSlotChange(idx, e.target.value)}
                    required
                    style={{ textAlign: 'center', fontWeight: 'bold' }}
                  />
                </div>
              ))}
            </div>
          </div>

          <button type="submit" className="btn-primary" disabled={savingTimes} style={{ marginTop: '12px' }}>
            <Save className="w-4 h-4" />
            <span>{savingTimes ? 'Salvando Horários...' : '💾 Salvar Horários de Autoposting'}</span>
          </button>
        </form>
      </div>

      {/* 3. SEÇÃO DE REDES SOCIAIS E PRIVACIDADE */}
      <div className="settings-card">
        <h3 className="settings-card-title">
          <Share2 className="w-5 h-5 text-purple-400" />
          <span>📱 Padrão de Redes Sociais & Privacidade</span>
        </h3>

        <form onSubmit={handleSaveSocialSubmit}>
          <div style={{ marginBottom: '20px' }}>
            <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '12px' }}>
              Plataformas Alvo de Publicação:
            </span>

            <div className="toggle-row">
              <div>
                <strong style={{ color: '#fff', fontSize: '0.9rem' }}>YouTube Vídeo Longo</strong>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar episódios longos no canal do YouTube</p>
              </div>
              <label className="toggle-switch">
                <input type="checkbox" checked={postYoutube} onChange={(e) => setPostYoutube(e.target.checked)} />
                <span className="slider"></span>
              </label>
            </div>

            <div className="toggle-row">
              <div>
                <strong style={{ color: '#fff', fontSize: '0.9rem' }}>YouTube Shorts</strong>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar formato vertical no Shorts</p>
              </div>
              <label className="toggle-switch">
                <input type="checkbox" checked={postShorts} onChange={(e) => setPostShorts(e.target.checked)} />
                <span className="slider"></span>
              </label>
            </div>

            <div className="toggle-row">
              <div>
                <strong style={{ color: '#fff', fontSize: '0.9rem' }}>TikTok</strong>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar automaticamente na conta do TikTok</p>
              </div>
              <label className="toggle-switch">
                <input type="checkbox" checked={postTiktok} onChange={(e) => setPostTiktok(e.target.checked)} />
                <span className="slider"></span>
              </label>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Lock className="w-4 h-4 text-cyan-400" />
              <span>Privacidade Padrão de Publicação:</span>
            </label>
            <select 
              className="form-select" 
              value={tiktokPrivacy} 
              onChange={(e) => setTiktokPrivacy(e.target.value)}
            >
              <option value="PUBLIC">🌐 Público (Recomendado)</option>
              <option value="PRIVATE">🔒 Privado (Apenas Você)</option>
              <option value="MUTUAL_FRIENDS">👥 Amigos Múltuos</option>
            </select>
          </div>

          <button type="submit" className="btn-primary" disabled={savingSocial} style={{ marginTop: '12px' }}>
            <Save className="w-4 h-4" />
            <span>{savingSocial ? 'Salvando Padrões...' : '💾 Salvar Padrões de Redes e Privacidade'}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
