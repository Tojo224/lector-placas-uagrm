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

export const AuthContext = createContext({
  user: null,
  authLoading: true,
  signInLoading: false,
  signUpLoading: false,
  profileSaving: false,
  authError: null,
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
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    const data = readSession();
    if (data?.user) {
      setUser(data.user);
    }
    setAuthLoading(false);
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
    setAuthError(null);

    try {
      const session = await loginUser(credentials);
      saveSession(session);
      setUser(session.user);
      return session;
    } catch (error) {
      setAuthError(error?.message || "Error al iniciar sesión");
      throw error;
    } finally {
      setSignInLoading(false);
    }
  };

  const signOut = async () => {
    await logoutUser();
    clearSession();
    setUser(null);
  };

  const signUp = async (payload) => {
    setSignUpLoading(true);
    setAuthError(null);

    try {
      const session = await registerUser(payload);
      saveSession(session);
      setUser(session.user);
      return session;
    } catch (error) {
      setAuthError(error?.message || "Error al registrarse");
      throw error;
    } finally {
      setSignUpLoading(false);
    }
  };

  const refreshProfile = async () => {
    try {
      const profile = await getProfile();
      persistUser(profile);
      return profile;
    } catch (error) {
      setAuthError(error?.message || "No se pudo cargar el perfil");
      throw error;
    }
  };

  const saveProfile = async (payload) => {
    setProfileSaving(true);
    setAuthError(null);
    try {
      const profile = await updateProfile(payload);
      persistUser(profile);
      return profile;
    } catch (error) {
      setAuthError(error?.message || "No se pudo guardar el perfil");
      throw error;
    } finally {
      setProfileSaving(false);
    }
  };

  const removeProfile = async () => {
    setProfileSaving(true);
    setAuthError(null);
    try {
      await deleteProfile();
      clearSession();
      setUser(null);
    } catch (error) {
      setAuthError(error?.message || "No se pudo eliminar el perfil");
      throw error;
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
        authError,
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
