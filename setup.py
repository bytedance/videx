from setuptools import setup, find_packages

with open('requirements.txt') as f:
    print('requirements.txt')
    install_requires = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    for ir in install_requires:
        print(f"-- install {ir}")

setup(
    name="videx",  # 添加这行
    version="0.0.1",  # 添加这行
    install_requires=install_requires,
    extras_require={
        'test': ['coverage'],
    },
    package_dir={'': 'src'},
    packages=find_packages(where='src'),  # 添加这行
)