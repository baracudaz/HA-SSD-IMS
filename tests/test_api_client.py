"""Test suite for SSD IMS API client."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.ssd_ims.api_client import SsdImsApiClient


class TestSsdImsApiClient:
    """Test suite for SSD IMS API client."""

    @pytest.fixture
    async def api_client(self):
        """Create API client instance for testing."""
        session = ClientSession()
        client = SsdImsApiClient(session)
        yield client
        await session.close()

    @pytest.fixture
    def mock_auth_response(self):
        """Mock authentication response."""
        return {
            "userProfile": {
                "userId": 15492,
                "username": "test_user",
                "fullName": "Test User",
                "email": "test@example.com",
                "createdOn": "2022-03-02T14:24:11.3012130Z",
                "changedOn": "2025-08-20T09:16:06.9163210Z",
            },
            "userActions": [10001, 10002, 10003],
            "passwordExpirationDate": "2025-09-30T11:43:43.8579390Z",
            "showPasswordChangeWarning": False,
        }

    @pytest.fixture
    def mock_pods_response(self):
        """Mock PODs response."""
        return [{"text": "99XXX1234560000G (Rodinný dom)", "value": "test_pod_id"}]

    @pytest.fixture
    def mock_chart_response(self):
        """Mock chart data response."""
        return {
            "meteringDatetime": ["2025-01-20T10:15:00.0000000Z"],
            "actualConsumption": [0.1320],
            "actualSupply": [0.0],
            "idleConsumption": [0.0],
            "idleSupply": [0.72],
            "sumActualConsumption": 16.7000,
            "sumActualSupply": 18.7760,
            "sumIdleConsumption": 0.0,
            "sumIdleSupply": 42.7910,
        }

    class TestAuthentication:
        """Test authentication functionality."""

        async def test_successful_authentication(self, api_client, mock_auth_response):
            """Test successful login with valid credentials."""
            with patch.object(api_client._session, "post") as mock_post:
                mock_response = AsyncMock()
                mock_response.json = AsyncMock(return_value=mock_auth_response)
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                result = await api_client.authenticate("test_user", "test_pass")

                assert result is True
                assert api_client._authenticated is True
                mock_post.assert_called_once()

        async def test_invalid_credentials(self, api_client):
            """Test authentication with invalid credentials."""
            with patch.object(api_client._session, "post") as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 401
                mock_post.return_value.__aenter__.return_value = mock_response

                result = await api_client.authenticate("invalid", "invalid")

                assert result is False
                assert api_client._authenticated is False

        async def test_network_error_during_auth(self, api_client):
            """Test handling of network errors during authentication."""
            with patch.object(api_client._session, "post") as mock_post:
                mock_post.side_effect = Exception("Network error")

                result = await api_client.authenticate("test_user", "test_pass")

                assert result is False
                assert api_client._authenticated is False

    class TestPointsOfDelivery:
        """Test POD discovery functionality."""

        async def test_successful_pod_discovery(self, api_client, mock_pods_response):
            """Test successful POD retrieval."""
            api_client._authenticated = True

            with patch.object(api_client._session, "get") as mock_get:
                mock_response = AsyncMock()
                mock_response.json = AsyncMock(return_value=mock_pods_response)
                mock_response.status = 200
                mock_get.return_value.__aenter__.return_value = mock_response

                pods = await api_client.get_points_of_delivery()

                assert len(pods) == 1
                assert pods[0].text == "99XXX1234560000G (Rodinný dom)"
                assert pods[0].value == "test_pod_id"

        async def test_empty_pods_response(self, api_client):
            """Test handling of empty POD response."""
            api_client._authenticated = True

            with patch.object(api_client._session, "get") as mock_get:
                mock_response = AsyncMock()
                mock_response.json = AsyncMock(return_value=[])
                mock_response.status = 200
                mock_get.return_value.__aenter__.return_value = mock_response

                pods = await api_client.get_points_of_delivery()

                assert len(pods) == 0

        async def test_unauthorized_pod_request(self, api_client):
            """Test POD request without authentication."""
            with patch.object(api_client._session, "get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 401
                mock_get.return_value.__aenter__.return_value = mock_response

                with pytest.raises(Exception):
                    await api_client.get_points_of_delivery()

    class TestChartData:
        """Test chart data retrieval."""

        async def test_successful_chart_retrieval(
            self, api_client, mock_chart_response
        ):
            """Test successful chart data retrieval."""
            api_client._authenticated = True
            pod_id = "99XXX1234560000G"
            from_date = datetime(2025, 1, 20, 0, 0)
            to_date = datetime(2025, 1, 20, 23, 59)

            with patch.object(api_client._session, "post") as mock_post:
                mock_response = AsyncMock()
                mock_response.json = AsyncMock(return_value=mock_chart_response)
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                chart_data = await api_client.get_chart_data(pod_id, from_date, to_date)

                assert chart_data.sum_actual_consumption == 16.7000
                assert chart_data.sum_actual_supply == 18.7760
                assert len(chart_data.metering_datetime) == 1
                assert len(chart_data.actual_consumption) == 1

        async def test_chart_data_with_none_values(self, api_client):
            """Test chart data handling with None values in arrays."""
            api_client._authenticated = True
            pod_id = "99XXX1234560000G"
            from_date = datetime(2025, 1, 20, 0, 0)
            to_date = datetime(2025, 1, 20, 23, 59)

            response_with_nones = {
                "meteringDatetime": [
                    "2025-01-20T10:15:00.0000000Z",
                    "2025-01-20T10:30:00.0000000Z",
                ],
                "actualConsumption": [0.1320, None],
                "actualSupply": [None, 0.5],
                "idleConsumption": [0.0, 0.0],
                "idleSupply": [0.72, 0.0],
                "sumActualConsumption": 16.7000,
                "sumActualSupply": 18.7760,
                "sumIdleConsumption": 0.0,
                "sumIdleSupply": 42.7910,
            }

            with patch.object(api_client._session, "post") as mock_post:
                mock_response = AsyncMock()
                mock_response.json = AsyncMock(return_value=response_with_nones)
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                chart_data = await api_client.get_chart_data(pod_id, from_date, to_date)

                assert len(chart_data.actual_consumption) == 2
                assert chart_data.actual_consumption[0] == 0.1320
                assert chart_data.actual_consumption[1] is None

    class TestErrorHandling:
        """Test error handling scenarios."""

        async def test_session_timeout(self, api_client):
            """Test handling of session timeouts."""
            api_client._authenticated = True

            with patch.object(api_client._session, "get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 408
                mock_get.return_value.__aenter__.return_value = mock_response

                with pytest.raises(Exception):
                    await api_client.get_points_of_delivery()

        async def test_rate_limiting(self, api_client):
            """Test handling of rate limiting responses."""
            api_client._authenticated = True

            with patch.object(api_client._session, "get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 429
                mock_get.return_value.__aenter__.return_value = mock_response

                with pytest.raises(Exception):
                    await api_client.get_points_of_delivery()

        async def test_server_error(self, api_client):
            """Test handling of server errors."""
            api_client._authenticated = True

            with patch.object(api_client._session, "get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 500
                mock_get.return_value.__aenter__.return_value = mock_response

                with pytest.raises(Exception):
                    await api_client.get_points_of_delivery()

    class TestSessionManagement:
        """Test session management functionality."""

        async def test_session_expiration_detection(self, api_client):
            """Test detection of session expiration."""
            mock_response = MagicMock()
            mock_response.headers = {"content-type": "text/html; charset=utf-8"}

            result = api_client._is_session_expired(mock_response)
            assert result is True

        async def test_session_not_expired(self, api_client):
            """Test detection when session is still valid."""
            mock_response = MagicMock()
            mock_response.headers = {"content-type": "application/json"}

            result = api_client._is_session_expired(mock_response)
            assert result is False

        async def test_reauthentication_with_stored_credentials(
            self, api_client, mock_auth_response
        ):
            """Test re-authentication with stored credentials."""
            api_client._username = "test_user"
            api_client._password = "test_pass"

            with patch.object(api_client, "authenticate") as mock_auth:
                mock_auth.return_value = True

                result = await api_client._reauthenticate()

                assert result is True
                mock_auth.assert_called_once_with("test_user", "test_pass")

        async def test_reauthentication_without_credentials(self, api_client):
            """Test re-authentication without stored credentials."""
            result = await api_client._reauthenticate()
            assert result is False

        async def test_logout_clears_credentials(self, api_client):
            """Test that logout clears stored credentials."""
            api_client._authenticated = True
            api_client._session_token = "test_token"
            api_client._username = "test_user"
            api_client._password = "test_pass"

            api_client.logout()

            assert api_client._authenticated is False
            assert api_client._session_token is None
            assert api_client._username is None
            assert api_client._password is None


class TestPodIdExtraction:
    """Test POD ID extraction from text."""

    @pytest.fixture
    async def api_client(self):
        """Create API client instance for testing."""
        session = ClientSession()
        client = SsdImsApiClient(session)
        yield client
        await session.close()

    async def test_pod_id_extraction(self, api_client):
        """Test that POD ID is correctly extracted from pod.text."""
        api_client._authenticated = True

        mock_response_data = [
            {"text": "99XXX1234560000G (Rodinný dom)", "value": "session_token_123"},
            {"text": "99YYY9876540000G (Garáž)", "value": "session_token_456"},
        ]

        with patch.object(api_client._session, "get") as mock_get:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response

            pods = await api_client.get_points_of_delivery()

            assert len(pods) == 2
            assert pods[0].id == "99XXX1234560000G"
            assert pods[1].id == "99YYY9876540000G"
