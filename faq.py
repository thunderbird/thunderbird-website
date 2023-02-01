# coding=utf-8
from helper import url


def get_entries(ctx):
    """Return a list of the faq entries. This requires context to retrieve some localized urls."""

    # Get the context set gettext
    gettext = ctx.environment.globals['gettext']

    # List of tuples - First index is the question, second is the answer. The formatting has to be done after gettext is evaluated.
    return [
            (
                gettext(u'What is Thunderbird’s relationship to MZLA Technologies Corporation?'),
                gettext(u'Thunderbird is a project of MZLA Technologies Corporation, which is a wholly owned subsidiary of Mozilla Foundation.')
            ),
            (
                gettext(u'What are the ways I can give?'),
                gettext(u'<a href="%(url)s">Visit this link to make a secure online donation right now via credit card or PayPal.</a>')
                % {'url': url(ctx, 'thunderbird.donate.ways-to-give')}
            ),
            (
                gettext(u'Why do you need my address in order to process a gift?'),
                gettext(u'We understand that your privacy is very important. We ask for a minimum amount of information required to process credit card payments, including billing addresses. This allows our payment processor to verify your identity, process your payment, and prevent fraudulent charges to your credit card. We keep your information private — if you have questions, please refer to our <a href="%(url)s">Privacy Policy</a>. If you would rather not fill in your information on our online form, you can mail us a check.')
                % {'url': url(ctx, 'privacy')}
            ),
            (
                gettext(u'Can I give bitcoin?'),
                gettext(u'We are not currently accepting bitcoin.'),
            ),
            (
                gettext(u'How can I turn off the appeal on the Thunderbird start page?'),
                gettext(u'The start page appeal to donate can’t currently be turned off. If you like, you can change the start page to something else. To do this, in Thunderbird go to Options | General'),
            ),
            (
                gettext(u'How will my gift be used?'),
                gettext(u'Thunderbird is the leading open source cross-platform email and calendaring client, free for business and personal use. Your gift will help ensure it stays that way, and will support future development.'),
            ),
            (
                gettext(u'Doesn’t Thunderbird earn income?'),
                gettext(u'Currently, the majority of Thunderbird’s revenue comes from generous gifts from users and friends of Thunderbird.'),
            ),
            (
                gettext(u'Who gives to Thunderbird?'),
                gettext(u'Anyone can give, companies and individuals, to Thunderbird to support development of the product now and in the future.')
            ),
            (
                gettext(u'Does my gift give me access to tech support?'),
                gettext(u'Anyone can access tech support for Thunderbird by visiting the <a href="%(url)s">support forum</a>. Thunderbird does not provide tech support or enhanced tech support in exchange for financial gifts.')
                % {'url': url(ctx, 'support')}
            ),
            (
                gettext(u'Is my gift tax deductible?'),
                gettext(u'Gifts to Thunderbird are not tax-deductible, but are greatly appreciated. Giving to Thunderbird supports the development of our leading open source cross-platform email and calendaring client, free for business and personal use. Your gift will help ensure it stays that way, and will support future development.'),
            ),
            (
                gettext(u'How do I cancel or change my recurring gift?'),
                gettext(u'If you used PayPal to set up a recurring gift, you’ll need to <a href="%(paypal)s">log in to your PayPal account</a> to make changes or to cancel. If you made a monthly gift using your credit card, please contact to the Donor Care team <a href="%(help)s">via this form</a>. Please include the email address and name you used to make your donation, and they’ll try to help you within two business days.')
                % {'paypal': 'https://www.paypal.com', 'help': 'https://give.thunderbird.net/help'}
            ),
            (
                gettext(u'Who can I email directly with questions about giving?'),
                gettext(u'If you have a question about giving to Thunderbird, please contact us via <a href="%(help)s">this form</a>. We will do our best to follow-up with you as soon as we can. If you need technical support, please head over to <a href="%(support)s">Thunderbird Support</a> for assistance.')
                % {'help': 'https://give.thunderbird.net/help', 'support': url(ctx, 'support')}
            )
    ]

