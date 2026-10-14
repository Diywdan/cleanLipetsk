import React, { useState } from 'react';
import { LogIn } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/entities/user/model/authStore';

// Вход в CRM. Учётные записи заводит администратор CRM: у ДРТ — все дела,
// у ведомства или УК — только дела своей организации.
export const LoginPage: React.FC = () => {
  const signIn = useAuthStore((s) => s.signIn);
  const error = useAuthStore((s) => s.error);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    await signIn(username.trim(), password);
    setBusy(false);
  };

  return (
    <div
      className="grid min-h-dvh place-items-center bg-background px-4 text-foreground"
      style={{ fontFamily: 'var(--font-ui)' }}
    >
      <form onSubmit={submit} className="glass w-full max-w-[360px] rounded-2xl p-6" aria-label="Вход">
        <div className="mb-6 flex items-center gap-3">
          <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden className="shrink-0 drop-shadow-[0_0_10px_var(--primary)]">
            <circle cx="15" cy="15" r="12.5" fill="none" stroke="var(--primary)" strokeOpacity="0.35" strokeWidth="1" />
            <circle cx="15" cy="15" r="8" fill="none" stroke="var(--primary)" strokeWidth="1.6" strokeDasharray="3 2.2" />
            <circle cx="15" cy="15" r="3" fill="var(--primary)" />
          </svg>
          <div className="leading-tight">
            <div className="eyebrow !text-[10px] !tracking-[0.24em] text-primary/90">Чистый Липецк</div>
            <div className="text-[15px] font-semibold">Ситуационный центр</div>
          </div>
        </div>

        <label className="mb-1.5 block text-[12.5px] text-muted-foreground" htmlFor="login-username">Логин</label>
        <Input
          id="login-username"
          autoComplete="username"
          autoFocus
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="mb-4 h-10"
        />
        <label className="mb-1.5 block text-[12.5px] text-muted-foreground" htmlFor="login-password">Пароль</label>
        <Input
          id="login-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-4 h-10"
        />

        {error && (
          <p role="alert" className="mb-4 rounded-lg bg-destructive/10 px-3 py-2 text-[13px] text-destructive">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" disabled={busy || !username || !password} className="h-10 w-full">
          <LogIn />
          {busy ? 'Входим…' : 'Войти'}
        </Button>
      </form>
    </div>
  );
};
