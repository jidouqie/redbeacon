"use client";

import { useEffect, useState } from "react";
import { api, Account } from "@/lib/api";
import AccountWriteCard from "./AccountWriteCard";

export default function WritePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    api.accounts.list()
      .then(setAccounts)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-sm mt-4" style={{ color: "var(--muted)" }}>加载中…</p>;

  if (accounts.length === 0) {
    return (
      <div className="space-y-2 mt-4">
        <h1 className="text-xl font-semibold">写文案</h1>
        <p className="text-sm" style={{ color: "var(--muted)" }}>暂无账号，请先在「账号管理」中添加账号。</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">写文案</h1>
        <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
          每个账号独立配置策略、选题库和文案风格。
        </p>
      </div>
      {accounts.map(acc => (
        <AccountWriteCard key={acc.id} account={acc} />
      ))}
    </div>
  );
}
