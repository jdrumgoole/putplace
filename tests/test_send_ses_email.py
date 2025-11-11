"""Tests for send_ses_email.py script."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_send_ses_email_import():
    """Test that the script can be imported."""
    from putplace.scripts import send_ses_email

    assert hasattr(send_ses_email, 'send_email')
    assert hasattr(send_ses_email, 'main')


def test_send_email_function():
    """Test send_email function with mocked boto3."""
    from putplace.scripts.send_ses_email import send_email

    with patch('boto3.Session') as mock_session:
        # Mock SES client
        mock_client = MagicMock()
        mock_client.send_email.return_value = {
            'MessageId': 'test-message-id-123',
            'ResponseMetadata': {
                'RequestId': 'test-request-id',
                'HTTPStatusCode': 200
            }
        }
        mock_session.return_value.client.return_value = mock_client

        # Send test email
        response = send_email(
            from_address='sender@example.com',
            to_addresses=['recipient@example.com'],
            subject='Test Subject',
            body='Test body content'
        )

        # Verify response
        assert response['MessageId'] == 'test-message-id-123'

        # Verify send_email was called correctly
        mock_client.send_email.assert_called_once()
        call_kwargs = mock_client.send_email.call_args[1]
        assert call_kwargs['Source'] == 'sender@example.com'
        assert call_kwargs['Destination']['ToAddresses'] == ['recipient@example.com']
        assert call_kwargs['Message']['Subject']['Data'] == 'Test Subject'
        assert call_kwargs['Message']['Body']['Text']['Data'] == 'Test body content'


def test_send_email_with_cc_bcc():
    """Test send_email with CC and BCC recipients."""
    from putplace.scripts.send_ses_email import send_email

    with patch('boto3.Session') as mock_session:
        mock_client = MagicMock()
        mock_client.send_email.return_value = {'MessageId': 'test-id'}
        mock_session.return_value.client.return_value = mock_client

        send_email(
            from_address='sender@example.com',
            to_addresses=['recipient@example.com'],
            subject='Test',
            body='Test',
            cc_addresses=['cc@example.com'],
            bcc_addresses=['bcc@example.com']
        )

        call_kwargs = mock_client.send_email.call_args[1]
        assert 'CcAddresses' in call_kwargs['Destination']
        assert call_kwargs['Destination']['CcAddresses'] == ['cc@example.com']
        assert 'BccAddresses' in call_kwargs['Destination']
        assert call_kwargs['Destination']['BccAddresses'] == ['bcc@example.com']


def test_send_email_html():
    """Test sending HTML email."""
    from putplace.scripts.send_ses_email import send_email

    with patch('boto3.Session') as mock_session:
        mock_client = MagicMock()
        mock_client.send_email.return_value = {'MessageId': 'test-id'}
        mock_session.return_value.client.return_value = mock_client

        html_body = '<h1>Hello</h1><p>This is HTML</p>'
        send_email(
            from_address='sender@example.com',
            to_addresses=['recipient@example.com'],
            subject='HTML Test',
            body=html_body,
            is_html=True
        )

        call_kwargs = mock_client.send_email.call_args[1]
        assert 'Html' in call_kwargs['Message']['Body']
        assert call_kwargs['Message']['Body']['Html']['Data'] == html_body
        assert 'Text' not in call_kwargs['Message']['Body']


def test_send_email_with_aws_profile():
    """Test send_email with AWS profile."""
    from putplace.scripts.send_ses_email import send_email

    with patch('boto3.Session') as mock_session:
        mock_client = MagicMock()
        mock_client.send_email.return_value = {'MessageId': 'test-id'}
        mock_session.return_value.client.return_value = mock_client

        send_email(
            from_address='sender@example.com',
            to_addresses=['recipient@example.com'],
            subject='Test',
            body='Test',
            aws_profile='my-profile'
        )

        # Verify Session was created with profile
        mock_session.assert_called_once()
        call_kwargs = mock_session.call_args[1]
        assert call_kwargs['profile_name'] == 'my-profile'


def test_main_simple_text_email():
    """Test main function with simple text email."""
    from putplace.scripts.send_ses_email import main

    test_args = [
        'send_ses_email.py',
        '--from', 'sender@example.com',
        '--to', 'recipient@example.com',
        '--subject', 'Test Email',
        '--body', 'This is a test message'
    ]

    with patch('sys.argv', test_args):
        with patch('boto3.Session') as mock_session:
            mock_client = MagicMock()
            mock_client.send_email.return_value = {
                'MessageId': 'test-id',
                'ResponseMetadata': {'RequestId': 'req-id', 'HTTPStatusCode': 200}
            }
            mock_session.return_value.client.return_value = mock_client

            result = main()
            assert result == 0
            mock_client.send_email.assert_called_once()


def test_main_multiple_recipients():
    """Test main with multiple recipients."""
    from putplace.scripts.send_ses_email import main

    test_args = [
        'send_ses_email.py',
        '--from', 'sender@example.com',
        '--to', 'user1@example.com', 'user2@example.com', 'user3@example.com',
        '--subject', 'Announcement',
        '--body', 'Important message'
    ]

    with patch('sys.argv', test_args):
        with patch('boto3.Session') as mock_session:
            mock_client = MagicMock()
            mock_client.send_email.return_value = {'MessageId': 'test-id', 'ResponseMetadata': {}}
            mock_session.return_value.client.return_value = mock_client

            result = main()
            assert result == 0

            call_kwargs = mock_client.send_email.call_args[1]
            assert len(call_kwargs['Destination']['ToAddresses']) == 3


def test_main_body_from_file():
    """Test main with body content from file."""
    from putplace.scripts.send_ses_email import main

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('Email body from file\nLine 2\nLine 3')
        body_file = f.name

    try:
        test_args = [
            'send_ses_email.py',
            '--from', 'sender@example.com',
            '--to', 'recipient@example.com',
            '--subject', 'File Test',
            '--body-file', body_file
        ]

        with patch('sys.argv', test_args):
            with patch('boto3.Session') as mock_session:
                mock_client = MagicMock()
                mock_client.send_email.return_value = {'MessageId': 'test-id', 'ResponseMetadata': {}}
                mock_session.return_value.client.return_value = mock_client

                result = main()
                assert result == 0

                call_kwargs = mock_client.send_email.call_args[1]
                assert 'Email body from file' in call_kwargs['Message']['Body']['Text']['Data']
    finally:
        Path(body_file).unlink()


def test_main_invalid_sender_email():
    """Test main with invalid sender email address."""
    from putplace.scripts.send_ses_email import main

    test_args = [
        'send_ses_email.py',
        '--from', 'invalid-email',
        '--to', 'recipient@example.com',
        '--subject', 'Test',
        '--body', 'Test'
    ]

    with patch('sys.argv', test_args):
        result = main()
        assert result == 1


def test_main_body_file_not_found():
    """Test main with non-existent body file."""
    from putplace.scripts.send_ses_email import main

    test_args = [
        'send_ses_email.py',
        '--from', 'sender@example.com',
        '--to', 'recipient@example.com',
        '--subject', 'Test',
        '--body-file', '/nonexistent/file.txt'
    ]

    with patch('sys.argv', test_args):
        result = main()
        assert result == 1


def test_main_ses_client_error():
    """Test main handling SES ClientError."""
    from putplace.scripts.send_ses_email import main
    from botocore.exceptions import ClientError

    test_args = [
        'send_ses_email.py',
        '--from', 'sender@example.com',
        '--to', 'recipient@example.com',
        '--subject', 'Test',
        '--body', 'Test'
    ]

    with patch('sys.argv', test_args):
        with patch('boto3.Session') as mock_session:
            mock_client = MagicMock()
            error_response = {
                'Error': {
                    'Code': 'MessageRejected',
                    'Message': 'Email address is not verified'
                }
            }
            mock_client.send_email.side_effect = ClientError(error_response, 'SendEmail')
            mock_session.return_value.client.return_value = mock_client

            result = main()
            assert result == 1


def test_main_no_credentials():
    """Test main handling missing AWS credentials."""
    from putplace.scripts.send_ses_email import main
    from botocore.exceptions import NoCredentialsError

    test_args = [
        'send_ses_email.py',
        '--from', 'sender@example.com',
        '--to', 'recipient@example.com',
        '--subject', 'Test',
        '--body', 'Test'
    ]

    with patch('sys.argv', test_args):
        with patch('boto3.Session') as mock_session:
            mock_session.return_value.client.side_effect = NoCredentialsError()

            result = main()
            assert result == 1


def test_main_verbose_output(capsys):
    """Test main with verbose output."""
    from putplace.scripts.send_ses_email import main

    test_args = [
        'send_ses_email.py',
        '--from', 'sender@example.com',
        '--to', 'recipient@example.com',
        '--subject', 'Test',
        '--body', 'Test message',
        '--verbose'
    ]

    with patch('sys.argv', test_args):
        with patch('boto3.Session') as mock_session:
            mock_client = MagicMock()
            mock_client.send_email.return_value = {
                'MessageId': 'msg-123',
                'ResponseMetadata': {'RequestId': 'req-123', 'HTTPStatusCode': 200}
            }
            mock_session.return_value.client.return_value = mock_client

            result = main()
            assert result == 0

            captured = capsys.readouterr()
            assert 'From: sender@example.com' in captured.out
            assert 'To: recipient@example.com' in captured.out
            assert 'Subject: Test' in captured.out
            assert 'Message ID: msg-123' in captured.out
