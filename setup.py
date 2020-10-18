from setuptools import setup
import versioneer

setup(name='reddit-chat-archiver',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      description='Reddit Chat Archiver',
      url='github.com/mikeage/reddit_chat_archiver',
      author='Mike Miller',
      author_email='github@mikeage.net',
      license='MIT',
      packages=['reddit_chat_archiver'],
      entry_points={
          'console_scripts': ['reddit-chat-archiver=reddit_chat_archiver.reddit_chat_archiver:main']
      },
      install_requires=[
          'colorama',
          'requests'
      ],
      zip_safe=False)
