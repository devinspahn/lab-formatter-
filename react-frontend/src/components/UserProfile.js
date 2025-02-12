import React from 'react';
import styles from './UserProfile.module.css';

const UserProfile = ({ username, onLogout }) => {
    return (
        <div className={styles.profileContainer}>
            <div className={styles.profileBox}>
                <h2>User Profile</h2>
                <div className={styles.profileInfo}>
                    <div className={styles.infoItem}>
                        <label>Username:</label>
                        <span>{username}</span>
                    </div>
                </div>
                <button onClick={onLogout} className={styles.logoutButton}>
                    Logout
                </button>
            </div>
        </div>
    );
};

export default UserProfile;
