# coding=utf-8
from helper import url


def get_entries(ctx):
    """Return a list of the faq entries. This requires context to retrieve some localized urls."""

    # Get the context set gettext
    gettext = ctx.environment.globals['gettext']

    # List of tuples - First index is the question, second is the answer. The formatting has to be done after gettext is evaluated.
    return [
            (
                gettext('What is Thunderbird’s relationship to MZLA Technologies Corporation?'),
                gettext('Thunderbird is a project of MZLA Technologies Corporation, which is a wholly owned subsidiary of Mozilla Foundation.')
            ),
            (
                gettext('Why do you need my address in order to process a gift?'),
                gettext('We understand that your privacy is very important. We ask for a minimum amount of information required to process credit card payments, including billing addresses. This allows our payment processor to verify your identity, process your payment, and prevent fraudulent charges to your credit card. We keep your information private — if you have questions, please refer to our <a href="%(url)s">Privacy Policy</a>. If you would rather not fill in your information on our online form, you can mail us a <a href="%(check)s">check</a>.')
                % {'url': url(ctx, 'privacy'), 'check': url(ctx, 'thunderbird.donate.ways-to-give.check')}
            ),
            (
                gettext('Can I give bitcoin?'),
                gettext('We are not currently accepting bitcoin.'),
            ),
            (
                gettext('How can I turn off the appeal on the Thunderbird start page?'),
                gettext('To learn how to customize your start page please visit:<br/><a href="%(url)s">%(url)s</a>')
                % {'url': 'https://support.mozilla.org/kb/how-disable-or-change-thunderbird-start-page'},
            ),
            (
                gettext('How will my gift be used?'),
                gettext('Thunderbird is the leading open source cross-platform email and calendaring client, free for business and personal use. Your gift will help ensure it stays that way, and will support future development.'),
            ),
            (
                gettext('Doesn’t Thunderbird earn income?'),
                gettext('Currently, the majority of Thunderbird’s revenue comes from generous gifts from users and friends of Thunderbird.'),
            ),
            (
                gettext('Who gives to Thunderbird?'),
                gettext('Anyone can give, companies and individuals, to support development of the product now and in the future.')
            ),
            (
                gettext('Does my gift give me access to tech support?'),
                gettext('Anyone can access tech support for Thunderbird by visiting the <a href="%(url)s">support forum</a>. Thunderbird does not provide tech support or enhanced tech support in exchange for financial gifts.')
                % {'url': url(ctx, 'support')}
            ),
            (
                gettext('Is my gift tax deductible?'),
                gettext('Gifts to Thunderbird are not tax-deductible, but are greatly appreciated. Giving to Thunderbird supports the development of our leading open source cross-platform email and calendaring client, free for business and personal use. Your gift will help ensure it stays that way, and will support future development.'),
            ),
            (
                gettext('How do I cancel or change my recurring gift?'),
                gettext('If you used PayPal to set up a recurring gift, you’ll need to <a href="%(paypal)s">log in to your PayPal account</a> to make changes or to cancel. If you made a monthly gift using your credit card, please contact the Donor Care team <a href="%(help)s">via this form</a>. Please include the email address and name you used to make your donation, and they’ll try to help you within two business days.')
                % {'paypal': 'https://www.paypal.com', 'help': url(ctx, 'thunderbird.donate.contact')}
            ),
            (
                gettext('Who can I email directly with questions about giving?'),
                gettext('If you have a question about giving to Thunderbird, please contact us via <a href="%(help)s">this form</a>. We will do our best to follow-up with you as soon as we can. If you need technical support, please head over to <a href="%(support)s">Thunderbird Support</a> for assistance.')
                % {'help': url(ctx, 'thunderbird.donate.contact'), 'support': url(ctx, 'support')}
            )
    ]
