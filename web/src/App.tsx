import React, { useState } from 'react';
import { UserProvider, useUser } from './context/UserContext';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ChatPage from './pages/ChatPage';
import styled from 'styled-components';

const AppContainer = styled.div`
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
`;

const AuthWrapper: React.FC = () => {
  const [showLogin, setShowLogin] = useState(true);
  const { user } = useUser();

  return (
    <>
      {user.isLogin ? (
        <ChatPage />
      ) : (
        showLogin ? (
          <LoginPage onSwitchToRegister={() => setShowLogin(false)} />
        ) : (
          <RegisterPage onSwitchToLogin={() => setShowLogin(true)} />
        )
      )}
    </>
  );
};

function App() {
  return (
    <AppContainer>
      <UserProvider>
        <AuthWrapper />
      </UserProvider>
    </AppContainer>
  );
}

export default App;
