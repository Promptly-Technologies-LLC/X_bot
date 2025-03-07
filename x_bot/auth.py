import logging
import base64
import hashlib
import os
import secrets
import time
from typing import Dict, Any, Optional
from requests_oauthlib import OAuth1, OAuth2Session

logger = logging.getLogger(__name__)

# Define the scopes needed for the OAuth2 flow
SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access", "media.write"]

def generate_code_verifier() -> str:
    """Generates a random code verifier string."""
    return secrets.token_urlsafe(100)

def generate_code_challenge(code_verifier: str) -> str:
    """Generates the code challenge from the code verifier."""
    code_challenge: bytes = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge_b64: str = base64.urlsafe_b64encode(code_challenge).decode()
    return code_challenge_b64.rstrip("=")

def create_oauth1_auth() -> OAuth1:
    """Create OAuth1 authentication object for media uploads."""
    return OAuth1(
        os.environ.get("X_API_KEY"),
        os.environ.get("X_API_SECRET"),
        os.environ.get("X_ACCESS_TOKEN"),
        os.environ.get("X_ACCESS_TOKEN_SECRET")
    )

def is_token_expired(token: Dict[str, Any]) -> bool:
    """Check if the token is expired or about to expire (within 5 minutes)."""
    if not token or 'expires_at' not in token:
        return True
    
    # Corrected expiration check with 5 minute buffer
    return token['expires_at'] <= time.time() + 300

def create_oauth2_session(token: Optional[Dict[str, Any]] = None) -> OAuth2Session:
    """
    Create an OAuth2 session for tweet posting. 
    If 'token' is provided, the session can manage refresh automatically.
    """
    client_id = os.environ.get("X_CLIENT_ID")
    client_secret = os.environ.get("X_CLIENT_SECRET")
    redirect_uri = os.environ.get("X_REDIRECT_URI")

    def token_updater(new_token: Dict[str, Any]) -> None:
        """Callback to save refreshed token."""
        from x_bot.session import save_token
        # Get user ID from the original token
        if token and 'user_id' in token:
            save_token(user_id=token['user_id'], token=new_token)

    session = OAuth2Session(
        client_id=client_id,
        token=token,
        scope=SCOPES,
        redirect_uri=redirect_uri,
        auto_refresh_url="https://api.x.com/2/oauth2/token",
        auto_refresh_kwargs={
            "client_id": client_id,
            "client_secret": client_secret,
        },
        token_updater=token_updater if token else None
    )

    return session

def refresh_token_if_needed(session: OAuth2Session, token: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Refresh the token if it's expired or about to expire."""
    try:
        # Check if the token is expired or about to expire
        if is_token_expired(token):
            print("Debug: Token is expired or about to expire, attempting refresh.")
            extra = {
                'client_id': os.environ.get("X_CLIENT_ID"),
                'client_secret': os.environ.get("X_CLIENT_SECRET"),
            }
            new_token = session.refresh_token(
                "https://api.x.com/2/oauth2/token",
                refresh_token=token['refresh_token'],
                **extra
            )
            print("Debug: Token successfully refreshed:", new_token)
            return new_token
        else:
            print("Debug: Token is still valid, no refresh needed.")
            return token
    except Exception as e:
        
        return None

def initialize_oauth_flow() -> tuple[OAuth2Session, str, str]:
    """
    Initialize a new OAuth flow.
    Returns (oauth_session, code_verifier, authorization_url)
    """
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    twitter_session = create_oauth2_session()
    
    authorization_url, oauth_state = twitter_session.authorization_url(
        "https://twitter.com/i/oauth2/authorize",
        code_challenge=code_challenge,
        code_challenge_method="S256"
    )
    
    return twitter_session, code_verifier, authorization_url, oauth_state

def exchange_code_for_token(
    twitter_session: OAuth2Session,
    code: str,
    code_verifier: str
) -> Optional[Dict[str, Any]]:
    """
    Exchange OAuth code for token.
    Returns the token if successful, None if failed.
    """
    try:
        token = twitter_session.fetch_token(
            token_url="https://api.x.com/2/oauth2/token",
            client_id=os.environ.get("X_CLIENT_ID"),
            client_secret=os.environ.get("X_CLIENT_SECRET"),
            code_verifier=code_verifier,
            code=code
        )
        return token
    except Exception as e:
        logger.error("Failed to fetch token: %s", str(e))
        return None