#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "upstream"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected source fragment not found in {path}: {old[:120]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"source fragment is not unique in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    oauth = ROOT / "app/src/main/kotlin/com/danielealbano/androidremotecontrolmcp/mcp/oauth/OAuthPolicy.kt"
    oauth_test = ROOT / "app/src/test/kotlin/com/danielealbano/androidremotecontrolmcp/mcp/oauth/OAuthPolicyTest.kt"
    server = ROOT / "app/src/main/kotlin/com/danielealbano/androidremotecontrolmcp/data/model/ServerConfig.kt"
    settings = ROOT / "app/src/main/kotlin/com/danielealbano/androidremotecontrolmcp/data/repository/SettingsRepositoryImpl.kt"
    settings_test = ROOT / "app/src/test/kotlin/com/danielealbano/androidremotecontrolmcp/data/repository/SettingsRepositoryImplTest.kt"

    replace_once(
        oauth,
        '    private const val CHATGPT_REDIRECT_PATH_PREFIX = "/connector/oauth/"\n\n',
        '''    private const val CHATGPT_REDIRECT_PATH_PREFIX = "/connector/oauth/"\n\n'''
        '''    /** Gemini custom MCP callbacks use Google's account-linking redirect service. */\n'''
        '''    private val GEMINI_REDIRECT_HOSTS =\n'''
        '''        setOf(\n'''
        '''            "oauth-redirect-sandbox.googleusercontent.com",\n'''
        '''            "oauth-redirect.googleusercontent.com",\n'''
        '''        )\n'''
        '''    private val GEMINI_REDIRECT_PATH_PREFIXES =\n'''
        '''        setOf(\n'''
        '''            "/r/custom-mcp-",\n'''
        '''            "/r/ground_custom-mcp-",\n'''
        '''        )\n\n'''
    )
    replace_once(
        oauth,
        '''        val isLoopback = parsed != null && parsed.scheme == "http" && host in LOOPBACK_HOSTS\n\n'''
        '''        return isChatGptConnectorCallback || isLoopback\n''',
        '''        val isGeminiCustomMcpCallback =\n'''
        '''            parsed != null &&\n'''
        '''                parsed.scheme == "https" &&\n'''
        '''                host in GEMINI_REDIRECT_HOSTS &&\n'''
        '''                parsed.port == -1 &&\n'''
        '''                parsed.rawUserInfo == null &&\n'''
        '''                parsed.rawQuery == null &&\n'''
        '''                parsed.rawFragment == null &&\n'''
        '''                parsed.path != null &&\n'''
        '''                GEMINI_REDIRECT_PATH_PREFIXES.any { prefix ->\n'''
        '''                    parsed.path.startsWith(prefix) && parsed.path.length > prefix.length\n'''
        '''                }\n'''
        '''        val isLoopback = parsed != null && parsed.scheme == "http" && host in LOOPBACK_HOSTS\n\n'''
        '''        return isChatGptConnectorCallback || isGeminiCustomMcpCallback || isLoopback\n'''
    )
    replace_once(
        oauth_test,
        '''        assertTrue(OAuthPolicy.isAllowedRedirectUri("https://chatgpt.com/connector/oauth/abc123"))\n''',
        '''        assertTrue(OAuthPolicy.isAllowedRedirectUri("https://chatgpt.com/connector/oauth/abc123"))\n'''
        '''        assertTrue(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com/r/custom-mcp-11573300372293581638"))\n'''
        '''        assertTrue(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect.googleusercontent.com/r/custom-mcp-123456789"))\n'''
        '''        assertTrue(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com/r/ground_custom-mcp-11573300372293581638"))\n'''
    )
    replace_once(
        oauth_test,
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("http://chatgpt.com/connector/oauth/abc"))\n''',
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("http://chatgpt.com/connector/oauth/abc"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com.evil.example/r/custom-mcp-1"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com@evil.example/r/custom-mcp-1"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("http://oauth-redirect-sandbox.googleusercontent.com/r/custom-mcp-1"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com/r/not-custom-mcp-1"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com:444/r/custom-mcp-1"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com/r/custom-mcp-1?x=1"))\n'''
        '''        assertFalse(OAuthPolicy.isAllowedRedirectUri("https://oauth-redirect-sandbox.googleusercontent.com/r/custom-mcp-1#x"))\n'''
    )

    replace_once(
        server,
        '    val cloudflareTunnelExtraArgs: String = "",\n',
        '    val cloudflareTunnelExtraArgs: String = DEFAULT_CLOUDFLARE_TUNNEL_EXTRA_ARGS,\n',
    )
    replace_once(
        server,
        '''        /** Default file size limit in megabytes. */\n        const val DEFAULT_FILE_SIZE_LIMIT_MB = 50\n''',
        '''        /** Default Cloudflare edge override used on networks where SRV/DNS tunnel discovery fails. */\n'''
        '''        const val DEFAULT_CLOUDFLARE_TUNNEL_EXTRA_ARGS = "--edge region1.v2.argotunnel.com:7844"\n\n'''
        '''        /** Default file size limit in megabytes. */\n        const val DEFAULT_FILE_SIZE_LIMIT_MB = 50\n'''
    )
    replace_once(
        settings,
        '        cloudflareTunnelExtraArgs = prefs[CLOUDFLARE_TUNNEL_EXTRA_ARGS_KEY] ?: "",\n',
        '        cloudflareTunnelExtraArgs = prefs[CLOUDFLARE_TUNNEL_EXTRA_ARGS_KEY] ?: ServerConfig.DEFAULT_CLOUDFLARE_TUNNEL_EXTRA_ARGS,\n',
    )
    replace_once(
        settings_test,
        '''        fun `defaults to empty when unset`() =\n            testScope.runTest {\n                val config = repository.getServerConfig()\n\n                assertEquals("", config.cloudflareTunnelExtraArgs)\n            }\n''',
        '''        fun `defaults to WEXSPACE edge override when unset`() =\n            testScope.runTest {\n                val config = repository.getServerConfig()\n\n                assertEquals(ServerConfig.DEFAULT_CLOUDFLARE_TUNNEL_EXTRA_ARGS, config.cloudflareTunnelExtraArgs)\n            }\n'''
    )

    print("WEXSPACE Android MCP R02 patch applied successfully")


if __name__ == "__main__":
    main()
