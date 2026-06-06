export interface StartGameGate {
  /**
   * 方案 A（先加载、就绪再跳转）下的导航闸门：
   *  · resolve(sessionId) —— 内容已就绪（首个 state_update / ending），落地 play 页可直接渲染舞台 → 跳转；
   *  · resolve(null)      —— 内容就绪前开局失败 → 不跳转，调用方留在 setup 页就地报错。
   */
  promise: Promise<string | null>;
  markSessionCreated: (sessionId: string) => void;
  markReady: () => void;
  markDone: () => void;
  markError: () => void;
}

export function createStartGameGate(): StartGameGate {
  let createdSessionId: string | null = null;
  let settled = false;
  let resolvePromise: (sessionId: string | null) => void = () => {};

  const promise = new Promise<string | null>((resolve) => {
    resolvePromise = resolve;
  });

  const settle = (sessionId: string | null) => {
    if (settled) {
      return;
    }

    settled = true;
    resolvePromise(sessionId);
  };

  return {
    promise,
    // session_id 到达只记录，不放行导航。继续等内容就绪，避免落地 play 页二次 loading。
    markSessionCreated: (sessionId) => {
      createdSessionId = sessionId;
    },
    // 内容就绪（首个 state_update 或 ending）—— 此刻 play 页能直接进舞台，放行导航。
    markReady: () => {
      settle(createdSessionId);
    },
    // 兜底：流跑完但没显式 ready（异常顺序），仍按已创建的 session 放行。
    markDone: () => {
      settle(createdSessionId);
    },
    // 内容就绪前失败：resolve null，不导航，让 setup 页就地显示错误（错误文案在 zustand error 里）。
    markError: () => {
      settle(null);
    },
  };
}
