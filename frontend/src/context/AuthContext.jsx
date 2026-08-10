import { createContext, useEffect, useState } from "react";
import {
  deleteProfile,
  getProfile,
  loginUser,
  logoutUser,
  registerUser,
  updateProfile
} from "../api/auth";
import { clearSession, readSession, saveSession } from "../services/storage";
import { getEdgeSession, isEdgeHosted, loginWithEdge, logoutFromEdge } from "../api/edge";

const EDGE_ROLES = new Set(["ADMINISTRADOR", "OPERADOR"]);

export const AuthContext = createContext({
  user: null,
  authLoading: true,
  signInLoading: false,
  signUpLoading: false,
  profileSaving: false,
  signIn: async () => {},
  signUp: async () => {},
  signOut: async () => {},
  refreshProfile: async () => {},
  saveProfile: async () => {},
  removeProfile: async () => {}
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [signInLoading, setSignInLoading] = useState(false);
  const [signUpLoading, setSignUpLoading] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);

  useEffect(() => {
    const restoreSession = async () => {
      const session = readSession();
      if (!session?.user) {
        setAuthLoading(false);
        return;
      }
      if (!isEdgeHosted) {
        setUser(session.user);
        setAuthLoading(false);
        return;
      }
      if (!EDGE_ROLES.has(session.user.rol)) {
        clearSession();
        setAuthLoading(false);
        return;
      }
      try {
        const current = await getEdgeSession();
        if (EDGE_ROLES.has(current.user?.rol)) setUser(current.user);
        else clearSession();
      } catch {
        clearSession();
      } finally {
        setAuthLoading(false);
      }
    };
    restoreSession();
  }, []);

  const persistUser = (nextUser) => {
    const currentSession = readSession();
    if (currentSession) {
      const nextSession = { ...currentSession, user: nextUser };
      saveSession(nextSession);
    }
    setUser(nextUser);
  };

  const signIn = async (credentials) => {
    setSignInLoading(true);

    try {
      const session = isEdgeHosted
        ? await loginWithEdge(credentials)
        : await loginUser(credentials);
      saveSession(session);
      setUser(session.user);
      return session;
    } finally {
      setSignInLoading(false);
    }
  };

  const signOut = async () => {
    if (isEdgeHosted) {
      try { await logoutFromEdge(); } catch { /* La sesión local se limpia igualmente. */ }
    } else {
      await logoutUser();
    }
    clearSession();
    setUser(null);
  };

  const signUp = async (payload) => {
    setSignUpLoading(true);

    try {
      const session = await registerUser(payload);
      saveSession(session);
      setUser(session.user);
      return session;
    } finally {
      setSignUpLoading(false);
    }
  };

  const refreshProfile = async () => {
    const profile = await getProfile();
    persistUser(profile);
    return profile;
  };

  const saveProfile = async (payload) => {
    setProfileSaving(true);
    try {
      const profile = await updateProfile(payload);
      persistUser(profile);
      return profile;
    } finally {
      setProfileSaving(false);
    }
  };

  const removeProfile = async () => {
    setProfileSaving(true);
    try {
      await deleteProfile();
      clearSession();
      setUser(null);
    } finally {
      setProfileSaving(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        authLoading,
        signInLoading,
        signUpLoading,
        profileSaving,
        signIn,
        signUp,
        signOut,
        refreshProfile,
        saveProfile,
        removeProfile
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
