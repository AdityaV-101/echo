import { createContext, useCallback, useContext, useEffect, useState } from "react";
import * as api from "./api";

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [userId, setUserId] = useState(() => localStorage.getItem("speechpal_user_id") || "");
  const [user, setUser] = useState(null);
  const [levelProgress, setLevelProgress] = useState({});
  const [phonemeErrors, setPhonemeErrors] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [levels, setLevels] = useState([]);
  const [practiceTracks, setPracticeTracks] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const applyProgress = (data) => {
    setUser(data.user);
    setLevelProgress(data.level_progress || {});
    setPhonemeErrors(data.phoneme_errors || []);
    setRecommendations(data.recommendations || []);
  };

  const loadStaticData = useCallback(async () => {
    const [lvls, tracks] = await Promise.all([api.getLevels(), api.getPracticeTracks()]);
    setLevels(lvls);
    setPracticeTracks(tracks);
  }, []);

  useEffect(() => {
    loadStaticData().catch((e) => setError(e.message));
  }, [loadStaticData]);

  useEffect(() => {
    if (!userId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .login(userId)
      .then((data) => {
        applyProgress(data);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [userId]);

  const doLogin = useCallback(async (id) => {
    setLoading(true);
    setError("");
    try {
      const data = await api.login(id);
      localStorage.setItem("speechpal_user_id", id);
      setUserId(id);
      applyProgress(data);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshProgress = useCallback(async () => {
    if (!userId) return;
    const data = await api.getProgress(userId);
    applyProgress(data);
  }, [userId]);

  const saveSettings = useCallback(
    async (speakAloud, speechRate, appSpeechEnabled) => {
      if (!userId) return;
      const resolvedAppSpeechEnabled =
        appSpeechEnabled === undefined ? !!user?.app_speech_enabled : appSpeechEnabled;
      const updated = await api.updateSettings(userId, speakAloud, speechRate, resolvedAppSpeechEnabled);
      setUser(updated);
    },
    [userId, user]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("speechpal_user_id");
    setUserId("");
    setUser(null);
    setLevelProgress({});
    setPhonemeErrors([]);
    setRecommendations([]);
  }, []);

  const value = {
    userId,
    user,
    levelProgress,
    phonemeErrors,
    recommendations,
    levels,
    practiceTracks,
    loading,
    error,
    doLogin,
    refreshProgress,
    saveSettings,
    logout,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
